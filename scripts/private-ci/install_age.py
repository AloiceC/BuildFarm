from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

AGE_MODULE = "filippo.io/age/cmd/age@v1.2.1"


def main() -> int:
    go = shutil.which("go")
    if not go:
        print("AGE_SETUP status=FAIL reason=go-missing")
        return 1

    completed = subprocess.run(
        [go, "install", AGE_MODULE],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        print("AGE_SETUP status=FAIL")
        return 1

    env = subprocess.run(
        [go, "env", "GOPATH"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if env.returncode != 0:
        print("AGE_SETUP status=FAIL")
        return 1

    binary_dir = str(Path(env.stdout.strip()) / "bin")
    github_path = os.environ.get("GITHUB_PATH")
    if github_path:
        with open(github_path, "a", encoding="utf-8") as handle:
            handle.write(binary_dir + "\n")

    print("AGE_SETUP version=1.2.1 status=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
