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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", required=True)
    args = parser.parse_args()

    try:
        data = tomllib.loads(Path(args.adapter).read_text(encoding="utf-8"))
        if data.get("schema_version") != 1:
            raise ValueError("unsupported adapter schema")

        project_id = str(data["project_id"])
        source_repo = str(data["source_repo"])
        handoff_ref = str(data.get("handoff_ref", "ci/buildfarm"))
        manifest_path = str(data.get("manifest_path", "ci/buildfarm.toml"))

        if source_repo.count("/") != 1 or handoff_ref != "ci/buildfarm":
            raise ValueError("adapter violates BuildFarm v1 source rules")
        source_owner, source_name = source_repo.split("/", 1)

        write_output("project_id", project_id)
        write_output("source_repo", source_repo)
        write_output("source_owner", source_owner)
        write_output("source_name", source_name)
        write_output("handoff_ref", handoff_ref)
        write_output("manifest_path", manifest_path)
        print(f"ADAPTER project={project_id} status=PASS")
        return 0
    except Exception:
        print("ADAPTER status=FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
