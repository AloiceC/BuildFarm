from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TOKEN_RE = re.compile(r"(?i)(gh[psu]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})")
SOURCE_LINE_RE = re.compile(r"^\s*\d+\s*\|")
CARET_RE = re.compile(r"^\s*[\^~]+\s*$")


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
    source_text = str(source.resolve())
    text = text.replace(source_text, "<src>")
    text = TOKEN_RE.sub("<redacted>", text)

    cleaned: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if SOURCE_LINE_RE.match(line) or CARET_RE.match(line):
            continue
        if len(line) > 600:
            line = line[:600] + " …<truncated>"
        cleaned.append(line)

    cleaned = cleaned[-300:]
    result = "\n".join(cleaned).strip()
    if len(result) > 48000:
        result = result[-48000:]
    return result or "No sanitized diagnostic text was available."


class Runner:
    def __init__(self, source: Path, diagnostics: Path):
        self.source = source
        self.diagnostics = diagnostics
        self.diagnostics.mkdir(parents=True, exist_ok=True)
        self.failed_stage: str | None = None
        self.failure_text = ""
        self.total_start = time.monotonic()

    def stage(self, name: str, command: list[str], env: dict[str, str] | None = None) -> bool:
        started = time.monotonic()
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        try:
            completed = subprocess.run(
                command,
                cwd=self.source,
                env=merged_env,
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

        (self.diagnostics / f"{name}.log").write_text(output, encoding="utf-8")
        duration = time.monotonic() - started
        status = "PASS" if code == 0 else "FAIL"
        print(f"STAGE name={name} status={status} duration={duration:.1f}s")

        if code != 0:
            self.failed_stage = name
            self.failure_text = sanitize(output, self.source)
            return False
        return True

    def elapsed(self) -> float:
        return time.monotonic() - self.total_start


def flutter_command(*parts: str) -> list[str]:
    executable = shutil.which("flutter") or "flutter"
    return [executable, *parts]


def dart_command(*parts: str) -> list[str]:
    executable = shutil.which("dart") or "dart"
    return [executable, *parts]


def patch_android_min_sdk(source: Path, min_sdk: int) -> None:
    path = source / "android/app/build.gradle.kts"
    text = path.read_text(encoding="utf-8")
    original = "minSdk = flutter.minSdkVersion"
    replacement = f"minSdk = {min_sdk}"
    if original in text:
        text = text.replace(original, replacement)
    elif replacement not in text:
        raise RuntimeError("generated Android minSdk declaration was not recognized")
    path.write_text(text, encoding="utf-8")


def maybe_use_gradle_mirror(source: Path) -> str:
    wrapper = source / "android/gradle/wrapper/gradle-wrapper.properties"
    if not wrapper.is_file():
        return "official"
    text = wrapper.read_text(encoding="utf-8")
    match = re.search(r"gradle-([0-9.]+)-(bin|all)\.zip", text)
    if not match:
        return "official"
    version, classifier = match.groups()
    mirror = (
        "https://mirrors.aliyun.com/github/releases/gradle/"
        f"gradle-distributions/v{version}/gradle-{version}-{classifier}.zip"
    )
    req = urllib.request.Request(mirror, method="HEAD", headers={"User-Agent": "AloiceC-BuildFarm-v1"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if not (200 <= response.status < 400):
                return "official"
    except Exception:
        return "official"

    text = re.sub(
        r"distributionUrl=.*gradle-[0-9.]+-(?:bin|all)\.zip",
        "distributionUrl=" + mirror.replace(":", "\\:"),
        text,
    )
    wrapper.write_text(text, encoding="utf-8")
    return "aliyun"


def load_manifest(source: Path, relative: str) -> dict:
    path = (source / relative).resolve()
    if source.resolve() not in path.parents:
        raise RuntimeError("manifest path escaped source")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def remove_build_tree(source: Path) -> None:
    build = source / "build"
    if build.exists():
        shutil.rmtree(build, ignore_errors=True)


def write_result(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--diagnostics", required=True)
    args = parser.parse_args()

    source = Path(args.source_dir).resolve()
    result_path = Path(args.result).resolve()
    diagnostics = Path(args.diagnostics).resolve()
    runner = Runner(source, diagnostics)
    task = args.task
    encrypted_path: Path | None = None
    raw_package: Path | None = None
    binary_size: int | None = None
    binary_hash: str | None = None
    encrypted_size: int | None = None
    encrypted_hash: str | None = None

    result = {
        "success": False,
        "task": task,
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
        flutter = manifest["flutter"]
        check = manifest["check"]
        android = manifest["android"]
        windows = manifest["windows"]
        delivery = manifest["delivery"]

        if task == "check":
            platforms = list(flutter["generated_platforms"])
        elif task.endswith("android"):
            platforms = ["android"]
        elif task.endswith("windows"):
            platforms = ["windows"]
        else:
            raise RuntimeError("unsupported BuildFarm task")

        create_args = [
            "create",
            "--project-name",
            str(flutter["project_name"]),
            "--org",
            str(flutter["organization"]),
            "--platforms=" + ",".join(platforms),
            ".",
        ]
        if not runner.stage("flutter_create", flutter_command(*create_args)):
            raise RuntimeError("private stage failed")

        if bool(flutter.get("remove_generated_widget_test", True)):
            (source / "test/widget_test.dart").unlink(missing_ok=True)

        if "android" in platforms:
            patch_android_min_sdk(source, int(android["min_sdk"]))
            mirror = maybe_use_gradle_mirror(source)
            print(f"MIRROR gradle={mirror} status=PASS")

        mirror_env = {
            "PUB_HOSTED_URL": os.environ.get("PUB_HOSTED_URL", "https://pub.dev"),
            "FLUTTER_STORAGE_BASE_URL": os.environ.get(
                "FLUTTER_STORAGE_BASE_URL", "https://storage.googleapis.com"
            ),
        }
        if not runner.stage("pub_get", flutter_command("pub", "get"), env=mirror_env):
            if mirror_env["PUB_HOSTED_URL"] != "https://pub.dev":
                print("STAGE name=pub_get_fallback mirror=official")
                runner.failed_stage = None
                runner.failure_text = ""
                official_env = {
                    "PUB_HOSTED_URL": "https://pub.dev",
                    "FLUTTER_STORAGE_BASE_URL": "https://storage.googleapis.com",
                }
                if not runner.stage("pub_get_official", flutter_command("pub", "get"), env=official_env):
                    raise RuntimeError("private stage failed")
            else:
                raise RuntimeError("private stage failed")

        if bool(flutter.get("run_build_runner", True)):
            if not runner.stage(
                "build_runner", dart_command("run", "build_runner", "build")
            ):
                raise RuntimeError("private stage failed")

        if task == "check":
            if bool(check.get("analyze", True)):
                if not runner.stage("analyze", flutter_command("analyze")):
                    raise RuntimeError("private stage failed")
            if bool(check.get("test", True)):
                if not runner.stage("test", flutter_command("test")):
                    raise RuntimeError("private stage failed")
        elif task.endswith("windows"):
            mode = str(windows.get("build_mode", "release"))
            if not runner.stage("windows_build", flutter_command("build", "windows", f"--{mode}")):
                raise RuntimeError("private stage failed")
            output_dir = source / str(windows["output_dir"])
            if not output_dir.is_dir():
                raise RuntimeError("Windows output directory missing")
            temp_base = Path(tempfile.mkdtemp(prefix="buildfarm-package-")) / (
                f"pixiv-lite-app-{args.sha[:12]}-windows"
            )
            archive = shutil.make_archive(str(temp_base), "zip", output_dir)
            raw_package = Path(archive)
        elif task.endswith("android"):
            mode = str(android.get("build_mode", "debug"))
            if not runner.stage("android_build", flutter_command("build", "apk", f"--{mode}")):
                raise RuntimeError("private stage failed")
            output = source / str(android["output"])
            if not output.is_file():
                raise RuntimeError("Android output file missing")
            temp_dir = Path(tempfile.mkdtemp(prefix="buildfarm-package-"))
            raw_package = temp_dir / f"pixiv-lite-app-{args.sha[:12]}-android.apk"
            shutil.copy2(output, raw_package)

        if raw_package is not None:
            binary_size = raw_package.stat().st_size
            binary_hash = sha256(raw_package)
            print(
                f"BINARY task={task} bytes={binary_size} sha256={binary_hash}"
            )

            if task.startswith("deliver-"):
                recipient = str(delivery.get("age_recipient", "")).strip()
                if not recipient:
                    raise RuntimeError("age recipient is not configured")
                age = shutil.which("age") or shutil.which("age.exe")
                if not age:
                    raise RuntimeError("age executable is not available")
                encrypted_path = raw_package.with_suffix(raw_package.suffix + ".age")
                if not runner.stage(
                    "age_encrypt",
                    [age, "-r", recipient, "-o", str(encrypted_path), str(raw_package)],
                ):
                    raise RuntimeError("private stage failed")
                encrypted_size = encrypted_path.stat().st_size
                encrypted_hash = sha256(encrypted_path)
                raw_package.unlink(missing_ok=True)
                raw_package = None
                print(
                    f"DELIVERY ciphertext_bytes={encrypted_size} sha256={encrypted_hash}"
                )
            else:
                raw_package.unlink(missing_ok=True)
                raw_package = None

        remove_build_tree(source)
        result["success"] = True
    except Exception as exc:
        if runner.failed_stage is None:
            runner.failed_stage = "buildfarm_adapter"
            runner.failure_text = sanitize(
                f"{type(exc).__name__}: {str(exc)}", source
            )
        remove_build_tree(source)
        if raw_package is not None:
            raw_package.unlink(missing_ok=True)
    finally:
        result["duration_seconds"] = round(runner.elapsed(), 2)
        result["failed_stage"] = runner.failed_stage
        result["binary_size"] = binary_size
        result["binary_sha256"] = binary_hash
        if encrypted_path is not None and encrypted_path.is_file():
            result["encrypted_path"] = str(encrypted_path)
            result["encrypted_size"] = encrypted_size
            result["encrypted_sha256"] = encrypted_hash
        if not result["success"]:
            diagnostics.mkdir(parents=True, exist_ok=True)
            (diagnostics / "sanitized.txt").write_text(
                runner.failure_text, encoding="utf-8"
            )
        write_result(result_path, result)
        gh_output("success", str(bool(result["success"])).lower())
        gh_output("encrypted_path", result["encrypted_path"] or "")
        gh_output("binary_sha256", result["binary_sha256"] or "")
        gh_output("encrypted_sha256", result["encrypted_sha256"] or "")
        status = "PASS" if result["success"] else "FAIL"
        print(
            f"TASK name={task} sha={args.sha} status={status} "
            f"duration={result['duration_seconds']:.1f}s"
        )

    # Always return zero here so the private Check Run can be posted first.
    return 0


if __name__ == "__main__":
    sys.exit(main())
