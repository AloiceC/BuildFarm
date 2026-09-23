from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

API = "https://api.github.com"
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SAFE_PERMISSION_RE = re.compile(r"[^A-Za-z0-9_=,; ._-]")


class GitSourceError(Exception):
    def __init__(self, reason: str = "git-failure") -> None:
        super().__init__(reason)
        self.reason = reason


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


def run_git(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitSourceError("git-launch") from exc


def classify_git_failure(stderr: str) -> str:
    text = stderr.lower()
    if "authentication failed" in text or "could not read username" in text:
        return "auth"
    if "repository not found" in text or "not found" in text:
        return "source-not-found"
    if "couldn't find remote ref" in text or "not our ref" in text:
        return "source-sha"
    if "could not resolve host" in text or "failed to connect" in text:
        return "network"
    return "git-failure"


def remove_tree(path: Path) -> None:
    if not path.exists():
        return

    def make_writable_and_retry(func, raw_path, exc_info):
        try:
            os.chmod(raw_path, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass
        func(raw_path)

    shutil.rmtree(path, onerror=make_writable_and_retry)


def pat_git_environment(token: str) -> dict[str, str]:
    # Match GitHub's mature HTTPS Git transport pattern without persisting the
    # credential in .git/config or putting it on the command line. Git reads
    # these config entries only from this child-process environment.
    credential = base64.b64encode(
        f"x-access-token:{token}".encode("utf-8")
    ).decode("ascii")
    env = os.environ.copy()
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {credential}",
        }
    )
    return env


def release_pat_git_environment(env: dict[str, str]) -> None:
    env["GIT_CONFIG_VALUE_0"] = "AUTHORIZATION: basic <released>"


def resolve_sha_with_git(repo: str, ref: str, token: str) -> str:
    git_env = pat_git_environment(token)
    remote = f"https://github.com/{repo}.git"
    remote_ref = ref if ref.startswith("refs/") else f"refs/heads/{ref}"
    try:
        result = run_git(
            ["ls-remote", "--exit-code", remote, remote_ref],
            Path.cwd(),
            git_env,
        )
        if result.returncode != 0:
            raise GitSourceError(classify_git_failure(result.stderr))
        first_line = next((line for line in result.stdout.splitlines() if line.strip()), "")
        sha = first_line.split(maxsplit=1)[0].strip().lower() if first_line else ""
        if not SHA_RE.fullmatch(sha):
            raise GitSourceError("source-sha")
        return sha
    finally:
        release_pat_git_environment(git_env)


def fetch_exact_with_git(repo: str, sha: str, token: str, destination: Path) -> Path:
    try:
        remove_tree(destination)
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise GitSourceError("workspace-setup") from exc

    git_env = pat_git_environment(token)

    try:
        result = run_git(["init", "--quiet"], destination, git_env)
        if result.returncode != 0:
            raise GitSourceError(classify_git_failure(result.stderr))

        remote = f"https://github.com/{repo}.git"
        result = run_git(
            ["fetch", "--quiet", "--no-tags", "--depth=1", remote, sha],
            destination,
            git_env,
        )
        if result.returncode != 0:
            raise GitSourceError(classify_git_failure(result.stderr))

        result = run_git(
            ["checkout", "--quiet", "--detach", "FETCH_HEAD"],
            destination,
            git_env,
        )
        if result.returncode != 0:
            raise GitSourceError(classify_git_failure(result.stderr))

        result = run_git(["rev-parse", "HEAD"], destination, git_env)
        resolved = result.stdout.strip().lower() if result.returncode == 0 else ""
        if resolved != sha.lower():
            raise GitSourceError("sha-mismatch")

        try:
            remove_tree(destination / ".git")
        except OSError as exc:
            raise GitSourceError("git-metadata-cleanup") from exc
        return destination
    finally:
        release_pat_git_environment(git_env)


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


def classify_http_error(exc: urllib.error.HTTPError) -> tuple[str, str]:
    accepted = ""
    try:
        accepted = exc.headers.get("X-Accepted-GitHub-Permissions", "") or ""
    except Exception:
        pass
    accepted = SAFE_PERMISSION_RE.sub("", accepted)[:200]

    message = ""
    try:
        raw = exc.read(4096)
        data = json.loads(raw.decode("utf-8", errors="replace"))
        message = str(data.get("message", "")).lower()
    except Exception:
        pass

    if "resource not accessible by personal access token" in message:
        reason = "pat-permission"
    elif "bad credentials" in message:
        reason = "bad-credentials"
    elif "secondary rate limit" in message:
        reason = "secondary-rate-limit"
    elif "rate limit exceeded" in message:
        reason = "rate-limit"
    elif "saml" in message or "single sign-on" in message:
        reason = "sso"
    else:
        reason = "github-http"
    return reason, accepted


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
    stage = "validate-input"
    try:
        if args.handoff_ref != "ci/buildfarm":
            raise ValueError("BuildFarm v1 handoff must be ci/buildfarm")

        if args.token_kind == "pat":
            if args.source_sha.strip():
                if not SHA_RE.fullmatch(args.source_sha.strip()):
                    raise ValueError("explicit source SHA must be a full 40-character SHA")
                sha = args.source_sha.strip().lower()
            else:
                stage = "resolve-sha-git"
                sha = resolve_sha_with_git(args.repo, args.handoff_ref, token)
        else:
            stage = "resolve-sha"
            sha = resolve_sha(args.repo, args.handoff_ref, args.source_sha, token)
        write_output("sha", sha)

        if args.task != "check":
            stage = "validate-prerequisite"
            if args.validation_backend == "commit-status":
                require_green_status(args.repo, sha, token, "BuildFarm / check")
            else:
                require_green_check(args.repo, sha, token, "BuildFarm / check")

        if args.token_kind == "pat":
            stage = "git-fetch"
            source_root = fetch_exact_with_git(args.repo, sha, token, Path(args.dest))
            token = ""
            os.environ.pop("BUILDFARM_SOURCE_TOKEN", None)
            write_output("source_dir", str(source_root))
            print(f"SOURCE sha={sha} status=PASS credential=step-scoped transport=git-header")
            return 0

        fd, raw_path = tempfile.mkstemp(prefix="buildfarm-source-", suffix=".zip")
        os.close(fd)
        tmp_zip = Path(raw_path)
        stage = "download-archive"
        download_archive(f"{API}/repos/{args.repo}/zipball/{sha}", token, tmp_zip)

        revoke(token)
        token_revoked = True
        token = ""
        os.environ.pop("BUILDFARM_SOURCE_TOKEN", None)

        stage = "extract-archive"
        dest = Path(args.dest)
        remove_tree(dest)
        source_root = safe_extract(tmp_zip, dest)
        write_output("source_dir", str(source_root))
        print(f"SOURCE sha={sha} status=PASS token=released")
        return 0
    except GitSourceError as exc:
        print(f"SOURCE status=FAIL stage={stage} reason={exc.reason}")
        return 1
    except urllib.error.HTTPError as exc:
        reason, accepted = classify_http_error(exc)
        suffix = f" accepted={accepted}" if accepted else ""
        print(f"SOURCE status=FAIL stage={stage} http={exc.code} reason={reason}{suffix}")
        return 1
    except urllib.error.URLError:
        print(f"SOURCE status=FAIL stage={stage} reason=network")
        return 1
    except ValueError:
        print(f"SOURCE status=FAIL stage={stage} reason=value-error")
        return 1
    except OSError as exc:
        print(
            f"SOURCE status=FAIL stage={stage} reason=os-error "
            f"type={type(exc).__name__}"
        )
        return 1
    except zipfile.BadZipFile:
        print(f"SOURCE status=FAIL stage={stage} reason=bad-zip")
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
