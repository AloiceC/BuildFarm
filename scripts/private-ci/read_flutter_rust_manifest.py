from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import sys
import tomllib


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        raise RuntimeError("GITHUB_OUTPUT is not available")
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def require_table(data: dict, name: str) -> dict:
    value = data.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"missing [{name}] table")
    return value


def safe_relative_path(raw: str) -> str:
    path = PurePosixPath(raw.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("path must stay inside the private source root")
    return path.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--expected-project", required=True)
    args = parser.parse_args()

    try:
        source = Path(args.source_dir).resolve()
        manifest = (source / args.manifest).resolve()
        if source != manifest and source not in manifest.parents:
            raise ValueError("manifest escaped source root")

        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1:
            raise ValueError("unsupported manifest schema")
        if data.get("project_id") != args.expected_project:
            raise ValueError("project id mismatch")
        if data.get("kind") != "flutter-rust":
            raise ValueError("unsupported project kind")

        app_dir = safe_relative_path(str(data["app_dir"]))
        app = (source / app_dir).resolve()
        if source not in app.parents or not (app / "pubspec.yaml").is_file():
            raise ValueError("Flutter app_dir is invalid")

        flutter = require_table(data, "flutter")
        rust = require_table(data, "rust")
        frb = require_table(data, "frb")
        check = require_table(data, "check")
        android = require_table(data, "android")
        windows = require_table(data, "windows")
        dependency = require_table(data, "dependency")

        generated = flutter.get("generated_platforms") or []
        if not isinstance(generated, list) or not generated:
            raise ValueError("generated_platforms must be a non-empty list")
        if any(str(item) not in {"android", "windows"} for item in generated):
            raise ValueError("unsupported generated platform")

        packages = rust.get("packages") or []
        if not isinstance(packages, list) or not packages:
            raise ValueError("rust packages must be a non-empty list")

        for key in ("manifest_overlay", "app_gradle_overlay"):
            rel = safe_relative_path(str(android[key]))
            if not (app / rel).is_file():
                raise ValueError(f"Android overlay missing: {key}")

        lock_required = bool(dependency.get("lockfile_required", False))
        if lock_required and not (app / "pubspec.lock").is_file():
            raise ValueError("required project lockfile is missing")

        outputs = {
            "app_dir": app_dir,
            "flutter_version": str(flutter["version"]),
            "flutter_channel": str(flutter.get("channel", "stable")),
            "java_version": str(android.get("java_version", "17")),
            "rust_toolchain": str(rust["toolchain"]),
            "frb_version": str(frb["version"]),
            "android_platform_package": str(android["platform_package"]),
            "android_build_tools": str(android["build_tools"]),
            "android_ndk_package": str(android["ndk_package"]),
        }

        for name, value in outputs.items():
            write_output(name, value)
        print("MANIFEST kind=flutter-rust status=PASS schema=1")
        return 0
    except Exception:
        print("MANIFEST kind=flutter-rust status=FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
