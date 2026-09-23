from __future__ import annotations

import argparse
import os
from pathlib import Path
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
        if data.get("kind") != "flutter":
            raise ValueError("unsupported project kind")

        flutter = require_table(data, "flutter")
        check = require_table(data, "check")
        android = require_table(data, "android")
        windows = require_table(data, "windows")
        dependency = require_table(data, "dependency")

        generated = flutter.get("generated_platforms") or []
        if not isinstance(generated, list) or not generated:
            raise ValueError("generated_platforms must be a non-empty list")

        lock_required = bool(dependency.get("lockfile_required", False))
        if lock_required and not (source / "pubspec.lock").is_file():
            raise ValueError("required project lockfile is missing")

        outputs = {
            "flutter_version": str(flutter["version"]),
            "flutter_channel": str(flutter.get("channel", "stable")),
            "flutter_project_name": str(flutter["project_name"]),
            "flutter_org": str(flutter["organization"]),
            "generated_platforms": ",".join(str(x) for x in generated),
            "remove_widget_test": str(bool(flutter.get("remove_generated_widget_test", True))).lower(),
            "run_build_runner": str(bool(flutter.get("run_build_runner", True))).lower(),
            "run_analyze": str(bool(check.get("analyze", True))).lower(),
            "run_test": str(bool(check.get("test", True))).lower(),
            "java_version": str(android.get("java_version", "17")),
            "android_build_mode": str(android.get("build_mode", "debug")),
            "android_min_sdk": str(int(android["min_sdk"])),
            "android_output": str(android["output"]),
            "windows_build_mode": str(windows.get("build_mode", "release")),
            "windows_output_dir": str(windows["output_dir"]),
        }

        for name, value in outputs.items():
            write_output(name, value)
        print("MANIFEST status=PASS schema=1")
        return 0
    except Exception:
        print("MANIFEST status=FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
