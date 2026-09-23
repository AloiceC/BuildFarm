from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    parser.add_argument("--delivery-upload", default="skipped")
    args = parser.parse_args()

    try:
        result = json.loads(Path(args.result).read_text(encoding="utf-8"))
        success = bool(result.get("success"))
        task = str(result.get("task", ""))
        if task.startswith("deliver-") and args.delivery_upload != "success":
            success = False
    except Exception:
        success = False

    print(f"FINAL status={'PASS' if success else 'FAIL'}")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
