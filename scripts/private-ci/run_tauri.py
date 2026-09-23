from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TOKEN_RE = re.compile(r"(?i)(gh[psu]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})")
SOURCE_LINE_RE = re.compile(r"^\s*\d+\s*[|:]\s")
CARET_RE = re.compile(r"^\s*[\^~]+\s*$")
UNIX_RUNNER_PATH_RE = re.compile(r"/(?:home|tmp)/runner(?:/[^\s:]+)+")
WINDOWS_RUNNER_PATH_RE = re.compile(r"[A-Za-z]:\\(?:a|runner|actions-runner)(?:\\[^\s:]+)+", re.IGNORECASE)

CHECK_STAGE_IDS = [
    "frontend-dependencies",
    "frontend-tests",
    "typescript",
    "frontend-build",
    "rust-toolchain",
    "rust-tests",
    "clippy",
]
WINDOWS_STAGE_IDS = [
    "frontend-dependencies",
    "rust-toolchain",
    "windows-build",
    "windows-checksum",
]


def gh_output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sanitize(text: str, source: Path) -> str:
    text = ANSI_RE.sub("", text)
    replacements = {
        str(source.resolve()): "<src>",
        os.environ.get("RUNNER_TEMP", ""): "<runner-temp>",
        os.environ.get("GITHUB_WORKSPACE", ""): "<workspace>",
    }
    for raw, replacement in replacements.items():
        if raw:
            text = text.replace(raw, replacement)
    text = UNIX_RUNNER_PATH_RE.sub("<runner-path>", text)
    text = WINDOWS_RUNNER_PATH_RE.sub("<runner-path>", text)
    text = TOKEN_RE.sub("<redacted>", text)

    cleaned: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if SOURCE_LINE_RE.match(line) or CARET_RE.match(line):
            continue
        if len(line) > 600:
            line = line[:600] + " …<truncated>"
        cleaned.append(line)

    result = "\n".join(cleaned[-300:]).strip()
    if len(result) > 48000:
        result = result[-48000:]
    return result or "No sanitized diagnostic text was available."


def safe_source_path(source: Path, raw: str) -> Path:
    relative = PurePosixPath(raw.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise RuntimeError("private manifest path escaped source root")
    candidate = source.joinpath(*relative.parts).resolve()
    if source != candidate and source not in candidate.parents:
        raise RuntimeError("private manifest path escaped source root")
    return candidate


def load_manifest(source: Path, relative: str) -> dict:
    return json.loads(safe_source_path(source, relative).read_text(encoding="utf-8"))


def write_result(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class Runner:
    def __init__(self, source: Path, diagnostics: Path):
        self.source = source
        self.diagnostics = diagnostics
        self.diagnostics.mkdir(parents=True, exist_ok=True)
        self.failed_stage: str | None = None
        self.failure_text = ""
        self.total_start = time.monotonic()

    def stage(self, stage_id: str, command: str) -> bool:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                ["pwsh", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
                cwd=self.source,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            output = completed.stdout or ""
            code = completed.returncode
        except Exception as exc:
            output = f"stage launch failed: {type(exc).__name__}"
            code = 127

        (self.diagnostics / f"{stage_id}.log").write_text(output, encoding="utf-8")
        duration = time.monotonic() - started
        status = "PASS" if code == 0 else "FAIL"
        print(f"STAGE name={stage_id} status={status} duration={duration:.1f}s")
        if code != 0:
            self.failed_stage = stage_id
            self.failure_text = sanitize(output, self.source)
            return False
        return True

    def elapsed(self) -> float:
        return time.monotonic() - self.total_start


def create_delivery_zip(source: Path, delivery: dict, sha: str) -> tuple[Path, int, str]:
    paths = delivery.get("paths") or []
    basename = str(delivery.get("artifact_basename", "private-build")).strip() or "private-build"
    temp_dir = Path(tempfile.mkdtemp(prefix="buildfarm-package-"))
    zip_path = temp_dir / f"{basename}-{sha[:12]}.zip"

    files: list[tuple[Path, str]] = []
    for raw in paths:
        file_path = safe_source_path(source, str(raw))
        if not file_path.is_file():
            raise RuntimeError("declared delivery file is missing")
        files.append((file_path, Path(str(raw)).name))

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path, archive_name in files:
            archive.write(file_path, arcname=archive_name)

    return zip_path, zip_path.stat().st_size, sha256(zip_path)


def remove_declared_delivery_files(source: Path, delivery: dict) -> None:
    for raw in delivery.get("paths") or []:
        try:
            safe_source_path(source, str(raw)).unlink(missing_ok=True)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--diagnostics", required=True)
    parser.add_argument("--age-recipient", default="")
    args = parser.parse_args()

    source = Path(args.source_dir).resolve()
    result_path = Path(args.result).resolve()
    diagnostics = Path(args.diagnostics).resolve()
    runner = Runner(source, diagnostics)
    encrypted_path: Path | None = None
    raw_package: Path | None = None

    result = {
        "success": False,
        "task": args.task,
        "source_sha": args.sha,
        "duration_seconds": 0.0,
        "failed_stage": None,
        "binary_size": None,
        "binary_sha256": None,
        "encrypted_path": None,
        "encrypted_size": None,
        "encrypted_sha256": None,
    }

    try:
        manifest = load_manifest(source, args.manifest)
        stages = {str(stage["id"]): stage for stage in manifest["stages"]}
        delivery = manifest["delivery"]

        if args.task == "check":
            selected = CHECK_STAGE_IDS
        elif args.task in {"build-windows", "deliver-windows"}:
            selected = WINDOWS_STAGE_IDS
        else:
            raise RuntimeError("unsupported BuildFarm Tauri task")

        for stage_id in selected:
            stage = stages.get(stage_id)
            if stage is None:
                raise RuntimeError("required Tauri stage is missing")
            if not runner.stage(stage_id, str(stage["command"])):
                raise RuntimeError("private stage failed")

        if args.task in {"build-windows", "deliver-windows"}:
            package, package_size, package_hash = create_delivery_zip(source, delivery, args.sha)
            raw_package = package
            result["binary_size"] = package_size
            result["binary_sha256"] = package_hash
            print(f"BINARY task={args.task} bytes={package_size} sha256={package_hash}")

            if args.task == "deliver-windows":
                recipient = args.age_recipient.strip()
                if not recipient:
                    raise RuntimeError("age recipient is not configured")
                age = shutil.which("age") or shutil.which("age.exe")
                if not age:
                    raise RuntimeError("age executable is not available")
                encrypted_path = package.with_suffix(package.suffix + ".age")
                started = time.monotonic()
                completed = subprocess.run(
                    [age, "-r", recipient, "-o", str(encrypted_path), str(package)],
                    cwd=source,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                duration = time.monotonic() - started
                print(f"STAGE name=age_encrypt status={'PASS' if completed.returncode == 0 else 'FAIL'} duration={duration:.1f}s")
                if completed.returncode != 0:
                    runner.failed_stage = "age_encrypt"
                    runner.failure_text = sanitize(completed.stdout or "", source)
                    raise RuntimeError("private stage failed")
                result["encrypted_path"] = str(encrypted_path)
                result["encrypted_size"] = encrypted_path.stat().st_size
                result["encrypted_sha256"] = sha256(encrypted_path)
                print(f"DELIVERY ciphertext_bytes={result['encrypted_size']} sha256={result['encrypted_sha256']}")

            raw_package.unlink(missing_ok=True)
            raw_package = None
            remove_declared_delivery_files(source, delivery)

        result["success"] = True
    except Exception as exc:
        if runner.failed_stage is None:
            runner.failed_stage = "buildfarm_adapter"
            runner.failure_text = sanitize(f"{type(exc).__name__}: {str(exc)}", source)
        if raw_package is not None:
            raw_package.unlink(missing_ok=True)
        try:
            manifest_for_cleanup = load_manifest(source, args.manifest)
            if isinstance(manifest_for_cleanup.get("delivery"), dict):
                remove_declared_delivery_files(source, manifest_for_cleanup["delivery"])
        except Exception:
            pass
    finally:
        result["duration_seconds"] = round(runner.elapsed(), 2)
        result["failed_stage"] = runner.failed_stage
        if not result["success"]:
            diagnostics.mkdir(parents=True, exist_ok=True)
            (diagnostics / "sanitized.txt").write_text(runner.failure_text, encoding="utf-8")
        write_result(result_path, result)
        gh_output("success", str(bool(result["success"])).lower())
        gh_output("encrypted_path", result["encrypted_path"] or "")
        gh_output("binary_sha256", result["binary_sha256"] or "")
        gh_output("encrypted_sha256", result["encrypted_sha256"] or "")
        status = "PASS" if result["success"] else "FAIL"
        print(f"TASK name={args.task} sha={args.sha} status={status} duration={result['duration_seconds']:.1f}s")

    # Let the shared Check Run reporter run before shared finalize determines job status.
    return 0


if __name__ == "__main__":
    sys.exit(main())
