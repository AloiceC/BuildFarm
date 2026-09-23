from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys


def remove(path: str) -> None:
    if not path:
        return
    target = Path(path)
    try:
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="")
    parser.add_argument("--encrypted", default="")
    parser.add_argument("--diagnostics", default="")
    parser.add_argument("--result", default="")
    args = parser.parse_args()

    remove(args.source)
    remove(args.encrypted)
    remove(args.diagnostics)
    remove(args.result)
    print("CLEANUP status=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
