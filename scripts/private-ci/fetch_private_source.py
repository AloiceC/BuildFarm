from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

API = "https://api.github.com"
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urllib.parse.urlparse(req.full_url)
        new = urllib.parse.urlparse(newurl)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and old.netloc != new.netloc:
            for key in list(redirected.headers):
                if key.lower() == "authorization":
                    del redirected.headers[key]
        return redirected


def request_json(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "AloiceC-BuildFarm-v1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def download_archive(url: str, token: str, destination: Path) -> None:
    opener = urllib.request.build_opener(SafeRedirectHandler())
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "AloiceC-BuildFarm-v1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with opener.open(req, timeout=90) as response, destination.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)


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


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def resolve_sha(repo: str, ref: str, explicit_sha: str, token: str) -> str:
    target = explicit_sha.strip() or ref
    if explicit_sha and not SHA_RE.fullmatch(explicit_sha.strip()):
        raise ValueError("explicit source SHA must be a full 40-character SHA")
    encoded = urllib.parse.quote(target, safe="")
    data = request_json(f"{API}/repos/{repo}/commits/{encoded}", token)
    sha = str(data.get("sha", ""))
    if not SHA_RE.fullmatch(sha):
        raise ValueError("GitHub did not resolve an exact commit SHA")
    if explicit_sha and sha.lower() != explicit_sha.lower():
        raise ValueError("explicit SHA resolution mismatch")
    return sha.lower()


def require_green_check(repo: str, sha: str, token: str, name: str) -> None:
    encoded_name = urllib.parse.quote(name, safe="")
    data = request_json(
        f"{API}/repos/{repo}/commits/{sha}/check-runs"
        f"?check_name={encoded_name}&filter=latest&per_page=100",
        token,
    )
    checks = data.get("check_runs") or []
    if not any(
        check.get("name") == name
        and check.get("status") == "completed"
        and check.get("conclusion") == "success"
        for check in checks
    ):
        raise ValueError("required private validation check is not green for this SHA")


def require_green_status(repo: str, sha: str, token: str, context: str) -> None:
    data = request_json(f"{API}/repos/{repo}/commits/{sha}/status?per_page=100", token)
    statuses = data.get("statuses") or []
    latest = next((item for item in statuses if item.get("context") == context), None)
    if latest is None or latest.get("state") != "success":
        raise ValueError("required private validation status is not green for this SHA")


def safe_extract(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            candidate = (dest / info.filename).resolve()
            if candidate != dest_resolved and dest_resolved not in candidate.parents:
                raise ValueError("archive path traversal rejected")
        archive.extractall(dest)

    roots = [p for p in dest.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise ValueError("unexpected GitHub archive layout")
    return roots[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--handoff-ref", default="ci/buildfarm")
    parser.add_argument("--source-sha", default="")
    parser.add_argument("--task", required=True)
    parser.add_argument("--dest", required=True)
    parser.add_argument("--token-kind", choices=("github-app", "pat"), default="github-app")
    parser.add_argument(
        "--validation-backend",
        choices=("check-run", "commit-status"),
        default="check-run",
    )
    args = parser.parse_args()

    token = os.environ.get("BUILDFARM_SOURCE_TOKEN", "")
    if not token:
        print("SOURCE status=FAIL reason=missing-token")
        return 1

    token_revoked = False
    tmp_zip: Path | None = None
    try:
        if args.handoff_ref != "ci/buildfarm":
            raise ValueError("BuildFarm v1 handoff must be ci/buildfarm")

        sha = resolve_sha(args.repo, args.handoff_ref, args.source_sha, token)
        write_output("sha", sha)

        if args.task != "check":
            if args.validation_backend == "commit-status":
                require_green_status(args.repo, sha, token, "BuildFarm / check")
            else:
                require_green_check(args.repo, sha, token, "BuildFarm / check")

        fd, raw_path = tempfile.mkstemp(prefix="buildfarm-source-", suffix=".zip")
        os.close(fd)
        tmp_zip = Path(raw_path)
        download_archive(f"{API}/repos/{args.repo}/zipball/{sha}", token, tmp_zip)

        if args.token_kind == "github-app":
            revoke(token)
            token_revoked = True
        token = ""
        os.environ.pop("BUILDFARM_SOURCE_TOKEN", None)

        dest = Path(args.dest)
        if dest.exists():
            shutil.rmtree(dest)
        source_root = safe_extract(tmp_zip, dest)
        write_output("source_dir", str(source_root))
        release_mode = "revoked" if args.token_kind == "github-app" else "step-scoped"
        print(f"SOURCE sha={sha} status=PASS credential={release_mode}")
        return 0
    except (ValueError, OSError, urllib.error.URLError, zipfile.BadZipFile):
        print("SOURCE status=FAIL")
        return 1
    finally:
        if tmp_zip is not None:
            try:
                tmp_zip.unlink(missing_ok=True)
            except OSError:
                pass
        if args.token_kind == "github-app" and not token_revoked and token:
            revoke(token)


if __name__ == "__main__":
    sys.exit(main())
