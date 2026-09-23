from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import sys

ALLOWED_STAGE_IDS = {
    "frontend-dependencies",
    "frontend-tests",
    "typescript",
    "frontend-build",
    "rust-toolchain",
    "rust-tests",
    "clippy",
    "windows-build",
    "windows-checksum",
}
REQUIRED_CHECK_STAGES = {
    "frontend-dependencies",
    "frontend-tests",
    "typescript",
    "frontend-build",
    "rust-toolchain",
    "rust-tests",
    "clippy",
}
REQUIRED_WINDOWS_STAGES = {
    "frontend-dependencies",
    "rust-toolchain",
    "windows-build",
    "windows-checksum",
}


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        raise RuntimeError("GITHUB_OUTPUT is not available")
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def safe_relative_path(raw: str) -> str:
    path = PurePosixPath(raw.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("delivery path must stay inside the private source root")
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

        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1:
            raise ValueError("unsupported manifest schema")
        if data.get("project_id") != args.expected_project:
            raise ValueError("project id mismatch")

        toolchains = data.get("toolchains")
        if not isinstance(toolchains, dict):
            raise ValueError("missing toolchains object")
        node_version = str(toolchains.get("node", "")).strip()
        if not node_version:
            raise ValueError("node toolchain version is required")

        stages = data.get("stages")
        if not isinstance(stages, list) or not stages:
            raise ValueError("stages must be a non-empty list")

        stage_ids: list[str] = []
        for stage in stages:
            if not isinstance(stage, dict):
                raise ValueError("stage must be an object")
            stage_id = str(stage.get("id", "")).strip()
            label = str(stage.get("label", "")).strip()
            command = stage.get("command")
            if stage_id not in ALLOWED_STAGE_IDS:
                raise ValueError("unsupported Tauri stage id")
            if stage_id in stage_ids:
                raise ValueError("duplicate Tauri stage id")
            if not label or not isinstance(command, str) or not command.strip():
                raise ValueError("stage label and command are required")
            stage_ids.append(stage_id)

        stage_set = set(stage_ids)
        if not REQUIRED_CHECK_STAGES.issubset(stage_set):
            raise ValueError("manifest is missing required check stages")
        if not REQUIRED_WINDOWS_STAGES.issubset(stage_set):
            raise ValueError("manifest is missing required Windows build stages")

        delivery = data.get("delivery")
        if not isinstance(delivery, dict):
            raise ValueError("missing delivery object")
        artifact_basename = str(delivery.get("artifact_basename", "")).strip()
        paths = delivery.get("paths")
        if not artifact_basename or not isinstance(paths, list) or not paths:
            raise ValueError("delivery artifact_basename and paths are required")
        for raw in paths:
            safe_relative_path(str(raw))

        write_output("node_version", node_version)
        print("MANIFEST kind=tauri status=PASS schema=1")
        return 0
    except Exception:
        print("MANIFEST kind=tauri status=FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
