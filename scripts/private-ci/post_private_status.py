from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

API = "https://api.github.com"
ISSUE_COUNT_RE = re.compile(r"\b(\d+)\s+(?:issue|issues)\s+found\b", re.IGNORECASE)


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


def compact_diagnostic(diagnostics_dir: str, failed_stage: str | None) -> str:
    if not diagnostics_dir or not failed_stage:
        return ""
    path = Path(diagnostics_dir) / "sanitized.txt"
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    lines = [" ".join(line.strip().split()) for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    if failed_stage == "analyze":
        count = ""
        for line in reversed(lines):
            match = ISSUE_COUNT_RE.search(line)
            if match:
                count = match.group(1)
                break

        diagnostic = ""
        for line in lines:
            if "•" not in line:
                continue
            parts = [part.strip() for part in line.split("•") if part.strip()]
            if len(parts) >= 3:
                code = parts[-1]
                location = parts[-2].replace("<src>/", "")
                diagnostic = f"{code} @ {location}"
            else:
                diagnostic = line
            break

        if diagnostic and count:
            return f"{count} issues; {diagnostic}"
        if diagnostic:
            return diagnostic
        if count:
            return f"{count} issues"

    ignored_prefixes = ("analyzing ", "no sanitized diagnostic text")
    for line in lines:
        if not line.lower().startswith(ignored_prefixes):
            return line[:100]
    return ""


def description(
    result: dict,
    success: bool,
    delivery: bool,
    upload_ok: bool,
    diagnostic: str = "",
) -> str:
    duration = result.get("duration_seconds", 0)
    if success:
        text = f"PASS · {duration}s"
    elif delivery and bool(result.get("success")) and not upload_ok:
        text = f"FAIL delivery-upload · {duration}s"
    elif result.get("failed_stage"):
        stage = str(result["failed_stage"])
        text = f"FAIL {stage}"
        if diagnostic:
            text += f" · {diagnostic}"
        else:
            text += f" · {duration}s"
    else:
        text = f"FAIL · {duration}s"
    return text[:140]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--diagnostics", default="")
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
        diagnostic = compact_diagnostic(args.diagnostics, result.get("failed_stage"))

        body = {
            "state": "success" if success else "failure",
            "context": status_context(args.task),
            "description": description(result, success, delivery, upload_ok, diagnostic),
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
