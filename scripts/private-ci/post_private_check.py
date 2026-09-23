from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request

API = "https://api.github.com"


def revoke(token: str) -> None:
    req = urllib.request.Request(
        f"{API}/installation/token",
        method="DELETE",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "AloiceC-BuildFarm-v1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20):
            pass
    except Exception:
        pass


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


def check_name(task: str) -> str:
    return f"BuildFarm / {task.replace('build-', '').replace('deliver-', 'deliver-')}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--diagnostics", required=True)
    parser.add_argument("--upload-outcome", default="skipped")
    args = parser.parse_args()

    token = os.environ.get("BUILDFARM_RESULT_TOKEN", "")
    if not token:
        print("CHECK_WRITE status=FAIL reason=missing-token")
        return 1

    try:
        result = json.loads(Path(args.result).read_text(encoding="utf-8"))
        build_ok = bool(result.get("success"))
        delivery = args.task.startswith("deliver-")
        upload_ok = not delivery or args.upload_outcome == "success"
        success = build_ok and upload_ok

        lines = [
            f"Task: `{args.task}`",
            f"Commit: `{args.sha}`",
            f"Result: `{'PASS' if success else 'FAIL'}`",
            f"Duration: `{result.get('duration_seconds', 0)}s`",
        ]
        if result.get("failed_stage"):
            lines.append(f"Failed stage: `{result['failed_stage']}`")
        if result.get("binary_size") is not None:
            lines.append(f"Binary bytes: `{result['binary_size']}`")
        if result.get("binary_sha256"):
            lines.append(f"Binary SHA-256: `{result['binary_sha256']}`")
        if result.get("encrypted_size") is not None:
            lines.append(f"Ciphertext bytes: `{result['encrypted_size']}`")
        if result.get("encrypted_sha256"):
            lines.append(f"Ciphertext SHA-256: `{result['encrypted_sha256']}`")
        if delivery and not upload_ok:
            lines.append("Encrypted artifact upload: `FAIL`")

        details = ""
        diagnostic = Path(args.diagnostics) / "sanitized.txt"
        if not success and diagnostic.is_file():
            details = diagnostic.read_text(encoding="utf-8")[-60000:]
        elif not success and delivery and not upload_ok:
            details = "The private build succeeded, but the encrypted delivery artifact could not be uploaded. No raw binary was published."

        body = {
            "name": check_name(args.task),
            "head_sha": args.sha,
            "status": "completed",
            "conclusion": "success" if success else "failure",
            "output": {
                "title": f"BuildFarm {args.task}: {'PASS' if success else 'FAIL'}",
                "summary": "\n\n".join(lines),
                "text": details,
            },
        }
        post_json(f"{API}/repos/{args.repo}/check-runs", token, body)
        print(f"CHECK_WRITE name={body['name']} status=PASS")
        return 0
    except Exception:
        print("CHECK_WRITE status=FAIL")
        return 1
    finally:
        revoke(token)


if __name__ == "__main__":
    sys.exit(main())
