from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request

API = "https://api.github.com"


def post_json(url: str, token: str, body: dict) -> dict:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "AloiceC-BuildFarm-v1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def status_context(task: str) -> str:
    return f"BuildFarm / {task.replace('build-', '').replace('deliver-', 'deliver-')}"


def description(result: dict, success: bool, delivery: bool, upload_ok: bool) -> str:
    duration = result.get("duration_seconds", 0)
    if success:
        text = f"PASS · {duration}s"
    elif delivery and bool(result.get("success")) and not upload_ok:
        text = f"FAIL delivery-upload · {duration}s"
    elif result.get("failed_stage"):
        text = f"FAIL {result['failed_stage']} · {duration}s"
    else:
        text = f"FAIL · {duration}s"
    return text[:140]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--upload-outcome", default="skipped")
    args = parser.parse_args()

    token = os.environ.get("BUILDFARM_RESULT_TOKEN", "")
    if not token:
        print("STATUS_WRITE status=FAIL reason=missing-token")
        return 1

    try:
        result = json.loads(Path(args.result).read_text(encoding="utf-8"))
        build_ok = bool(result.get("success"))
        delivery = args.task.startswith("deliver-")
        upload_ok = not delivery or args.upload_outcome == "success"
        success = build_ok and upload_ok

        body = {
            "state": "success" if success else "failure",
            "context": status_context(args.task),
            "description": description(result, success, delivery, upload_ok),
        }
        target_url = os.environ.get("BUILDFARM_TARGET_URL", "").strip()
        if target_url:
            body["target_url"] = target_url

        post_json(f"{API}/repos/{args.repo}/statuses/{args.sha}", token, body)
        print(
            f"STATUS_WRITE context={body['context']} "
            f"state={body['state']} status=PASS"
        )
        return 0
    except Exception:
        print("STATUS_WRITE status=FAIL")
        return 1
    finally:
        os.environ.pop("BUILDFARM_RESULT_TOKEN", None)


if __name__ == "__main__":
    sys.exit(main())
