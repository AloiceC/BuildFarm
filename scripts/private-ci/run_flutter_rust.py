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
import tomllib
import urllib.request

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TOKEN_RE = re.compile(r"(?i)(gh[psu]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})")
SOURCE_LINE_RE = re.compile(r"^\s*\d+\s*\|")
CARET_RE = re.compile(r"^\s*[\^~]+\s*$")
UNIX_RUNNER_PATH_RE = re.compile(r"/(?:home|tmp)/runner(?:/[^\s:]+)+")
WINDOWS_RUNNER_PATH_RE = re.compile(r"[A-Za-z]:\\(?:a|runner|actions-runner)(?:\\[^\s:]+)+", re.IGNORECASE)


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

    def stage(
        self,
        name: str,
        command: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> bool:
        started = time.monotonic()
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        try:
            completed = subprocess.run(
                command,
                cwd=cwd or self.source,
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


def safe_relative_path(raw: str) -> str:
    path = PurePosixPath(raw.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise RuntimeError("private manifest path escaped source")
    return path.as_posix()


def load_manifest(source: Path, relative: str) -> dict:
    path = (source / relative).resolve()
    if source.resolve() not in path.parents:
        raise RuntimeError("manifest path escaped source")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def copy_overlay(app: Path, relative_source: str, relative_target: str) -> None:
    src = (app / safe_relative_path(relative_source)).resolve()
    dst = (app / safe_relative_path(relative_target)).resolve()
    if app.resolve() not in src.parents or app.resolve() not in dst.parents:
        raise RuntimeError("overlay path escaped Flutter app")
    if not src.is_file():
        raise RuntimeError("required Android overlay is missing")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def patch_android_settings(app: Path, agp_version: str) -> None:
    path = app / "android/settings.gradle.kts"
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'id\("com\.android\.application"\)\s+version\s+"[^"]+"\s+apply false',
        f'id("com.android.application") version "{agp_version}" apply false',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("generated AGP declaration was not recognized")
    path.write_text(updated, encoding="utf-8")


def patch_gradle_wrapper(app: Path, gradle_version: str) -> str:
    path = app / "android/gradle/wrapper/gradle-wrapper.properties"
    text = path.read_text(encoding="utf-8")
    official = f"https\\://services.gradle.org/distributions/gradle-{gradle_version}-all.zip"
    updated, count = re.subn(
        r"distributionUrl=.*gradle-[0-9.]+-(?:bin|all)\.zip",
        f"distributionUrl={official}",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("generated Gradle wrapper declaration was not recognized")

    mirror = (
        "https://mirrors.aliyun.com/github/releases/gradle/"
        f"gradle-distributions/v{gradle_version}/gradle-{gradle_version}-all.zip"
    )
    req = urllib.request.Request(
        mirror,
        method="HEAD",
        headers={"User-Agent": "AloiceC-BuildFarm-v1"},
    )
    selected = "official"
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if 200 <= response.status < 400:
                updated = re.sub(
                    r"distributionUrl=.*gradle-[0-9.]+-(?:bin|all)\.zip",
                    "distributionUrl=" + mirror.replace(":", "\\:"),
                    updated,
                    count=1,
                )
                selected = "aliyun"
    except Exception:
        pass

    path.write_text(updated, encoding="utf-8")
    return selected


def cargo_packages(packages: list[str]) -> list[str]:
    result: list[str] = []
    for package in packages:
        result.extend(["-p", package])
    return result


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
    parser.add_argument("--age-recipient", default="")
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
        project_id = str(manifest["project_id"])
        app = (source / safe_relative_path(str(manifest["app_dir"]))).resolve()
        flutter = manifest["flutter"]
        rust = manifest["rust"]
        frb = manifest["frb"]
        check = manifest["check"]
        android = manifest["android"]
        windows = manifest["windows"]

        if source not in app.parents:
            raise RuntimeError("Flutter app escaped source root")

        if task == "check":
            platforms = list(flutter["generated_platforms"])
        elif task.endswith("android"):
            platforms = ["android"]
        elif task.endswith("windows"):
            platforms = ["windows"]
        else:
            raise RuntimeError("unsupported BuildFarm task")

        # Platform-independent Rust validation belongs to the exact-SHA check task.
        # Platform build/delivery tasks already require that private check to be green.
        if task != "check":
            rust = {**rust, "fmt": False, "clippy": False, "test": False}

        packages = [str(x) for x in rust["packages"]]
        package_args = cargo_packages(packages)

        if bool(rust.get("fmt", True)):
            if not runner.stage(
                "rust_fmt",
                ["cargo", "fmt", *package_args, "--", "--check"],
                cwd=source,
            ):
                raise RuntimeError("private stage failed")

        if bool(rust.get("clippy", True)):
            if not runner.stage(
                "rust_clippy",
                ["cargo", "clippy", *package_args, "--all-targets", "--", "-D", "warnings"],
                cwd=source,
            ):
                raise RuntimeError("private stage failed")

        if bool(rust.get("test", True)):
            if not runner.stage(
                "rust_test",
                ["cargo", "test", *package_args],
                cwd=source,
            ):
                raise RuntimeError("private stage failed")

        create_args = [
            "create",
            "--project-name",
            str(flutter["project_name"]),
            "--org",
            str(flutter["organization"]),
            "--platforms=" + ",".join(platforms),
            "--no-pub",
            ".",
        ]
        if not runner.stage("flutter_create", flutter_command(*create_args), cwd=app):
            raise RuntimeError("private stage failed")

        if "android" in platforms:
            copy_overlay(
                app,
                str(android["manifest_overlay"]),
                "android/app/src/main/AndroidManifest.xml",
            )
            copy_overlay(
                app,
                str(android["app_gradle_overlay"]),
                "android/app/build.gradle.kts",
            )
            patch_android_settings(app, str(android["agp_version"]))
            mirror = patch_gradle_wrapper(app, str(android["gradle_version"]))
            print(f"MIRROR gradle={mirror} status=PASS")

        mirror_env = {
            "PUB_HOSTED_URL": os.environ.get("PUB_HOSTED_URL", "https://pub.dev"),
            "FLUTTER_STORAGE_BASE_URL": os.environ.get(
                "FLUTTER_STORAGE_BASE_URL", "https://storage.googleapis.com"
            ),
        }
        if not runner.stage("pub_get", flutter_command("pub", "get"), cwd=app, env=mirror_env):
            if mirror_env["PUB_HOSTED_URL"] != "https://pub.dev":
                print("STAGE name=pub_get_fallback mirror=official")
                runner.failed_stage = None
                runner.failure_text = ""
                official_env = {
                    "PUB_HOSTED_URL": "https://pub.dev",
                    "FLUTTER_STORAGE_BASE_URL": "https://storage.googleapis.com",
                }
                if not runner.stage(
                    "pub_get_official",
                    flutter_command("pub", "get"),
                    cwd=app,
                    env=official_env,
                ):
                    raise RuntimeError("private stage failed")
            else:
                raise RuntimeError("private stage failed")

        frb_config = safe_relative_path(str(frb.get("config", "flutter_rust_bridge.yaml")))
        if not runner.stage(
            "frb_codegen",
            ["flutter_rust_bridge_codegen", "generate", "--config-file", frb_config],
            cwd=app,
        ):
            raise RuntimeError("private stage failed")

        if bool(flutter.get("run_build_runner", True)):
            build_runner = ["run", "build_runner", "build"]
            if bool(flutter.get("delete_conflicting_outputs", True)):
                build_runner.append("--delete-conflicting-outputs")
            if not runner.stage(
                "build_runner",
                dart_command(*build_runner),
                cwd=app,
            ):
                raise RuntimeError("private stage failed")

        if task == "check":
            if bool(check.get("analyze", True)):
                if not runner.stage("analyze", flutter_command("analyze"), cwd=app):
                    raise RuntimeError("private stage failed")
            if bool(check.get("test", True)):
                if not runner.stage("test", flutter_command("test"), cwd=app):
                    raise RuntimeError("private stage failed")
        elif task.endswith("windows"):
            mode = str(windows.get("build_mode", "release"))
            if not runner.stage(
                "windows_build",
                flutter_command("build", "windows", f"--{mode}"),
                cwd=app,
            ):
                raise RuntimeError("private stage failed")
            output_dir = app / safe_relative_path(str(windows["output_dir"]))
            if not output_dir.is_dir():
                raise RuntimeError("Windows output directory missing")
            temp_base = Path(tempfile.mkdtemp(prefix="buildfarm-package-")) / (
                f"{project_id}-{args.sha[:12]}-windows"
            )
            raw_package = Path(shutil.make_archive(str(temp_base), "zip", output_dir))
        elif task.endswith("android"):
            mode = str(android.get("build_mode", "release"))
            if not runner.stage(
                "android_build",
                flutter_command("build", "apk", f"--{mode}"),
                cwd=app,
            ):
                raise RuntimeError("private stage failed")
            output = app / safe_relative_path(str(android["output"]))
            if not output.is_file():
                raise RuntimeError("Android output file missing")
            temp_dir = Path(tempfile.mkdtemp(prefix="buildfarm-package-"))
            raw_package = temp_dir / f"{project_id}-{args.sha[:12]}-android.apk"
            shutil.copy2(output, raw_package)

        if raw_package is not None:
            binary_size = raw_package.stat().st_size
            binary_hash = sha256(raw_package)
            print(f"BINARY task={task} bytes={binary_size} sha256={binary_hash}")

            if task.startswith("deliver-"):
                recipient = args.age_recipient.strip()
                if not recipient:
                    raise RuntimeError("age recipient is not configured")
                age = shutil.which("age") or shutil.which("age.exe")
                if not age:
                    raise RuntimeError("age executable is not available")
                encrypted_path = raw_package.with_suffix(raw_package.suffix + ".age")
                if not runner.stage(
                    "age_encrypt",
                    [age, "-r", recipient, "-o", str(encrypted_path), str(raw_package)],
                    cwd=source,
                ):
                    raise RuntimeError("private stage failed")
                encrypted_size = encrypted_path.stat().st_size
                encrypted_hash = sha256(encrypted_path)
                raw_package.unlink(missing_ok=True)
                raw_package = None
                print(
                    f"DELIVERY ciphertext_bytes={encrypted_size} "
                    f"sha256={encrypted_hash}"
                )
            else:
                raw_package.unlink(missing_ok=True)
                raw_package = None

        result["success"] = True
    except Exception as exc:
        if runner.failed_stage is None:
            runner.failed_stage = "buildfarm_adapter"
            runner.failure_text = sanitize(f"{type(exc).__name__}: {str(exc)}", source)
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
                runner.failure_text,
                encoding="utf-8",
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

    # Let the workflow post the private Check Run before finalizing the job.
    return 0


if __name__ == "__main__":
    sys.exit(main())
