#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

BASELINE_FILENAME = "CORE_BASELINE.json"


class UpstreamUnavailable(RuntimeError):
    pass


def load_baseline(root: Path) -> dict:
    path = root / BASELINE_FILENAME
    if not path.is_file():
        raise SystemExit(f"Missing {BASELINE_FILENAME}: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid {BASELINE_FILENAME}: {exc}") from exc
    required = ["coreRepository", "coreCommit", "coreVersion", "distribution"]
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise SystemExit(f"{BASELINE_FILENAME} missing required field(s): {', '.join(missing)}")
    return data


def github_get_json(url: str, token: str | None) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "project-forge-core-upstream-check",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise UpstreamUnavailable(str(exc)) from exc


def resolve_remote_head(repository: str, ref: str, token: str | None, fetch: Callable[[str, str | None], dict]) -> str:
    quoted_ref = urllib.parse.quote(ref, safe="")
    data = fetch(f"https://api.github.com/repos/{repository}/commits/{quoted_ref}", token)
    sha = str(data.get("sha") or "").strip()
    if not sha:
        raise UpstreamUnavailable("GitHub response did not include a commit SHA")
    return sha


def compare_remote(
    repository: str,
    baseline_sha: str,
    upstream_sha: str,
    token: str | None,
    fetch: Callable[[str, str | None], dict],
) -> dict:
    return fetch(
        f"https://api.github.com/repos/{repository}/compare/{baseline_sha}...{upstream_sha}",
        token,
    )


def resolve_local_head(core_path: Path, ref: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(core_path), "rev-parse", ref],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise UpstreamUnavailable(f"unable to resolve {ref!r} in {core_path}") from exc
    return result.stdout.strip()


def check_upstream(
    root: Path,
    *,
    ref: str = "main",
    token: str | None = None,
    core_path: Path | None = None,
    skip_if_unavailable: bool = False,
    fetch: Callable[[str, str | None], dict] = github_get_json,
) -> int:
    root = root.resolve()
    baseline = load_baseline(root)
    repository = baseline["coreRepository"]
    baseline_sha = baseline["coreCommit"]

    try:
        if core_path is not None:
            upstream_sha = resolve_local_head(core_path.resolve(), ref)
            comparison = None
        else:
            upstream_sha = resolve_remote_head(repository, ref, token, fetch)
            comparison = None if upstream_sha == baseline_sha else compare_remote(
                repository, baseline_sha, upstream_sha, token, fetch
            )
    except UpstreamUnavailable as exc:
        if skip_if_unavailable:
            print(f"Core upstream freshness: SKIP ({exc})")
            return 0
        print(f"Core upstream freshness: UNAVAILABLE ({exc})")
        return 2

    print(f"Consumer baseline: {baseline['coreVersion']} @ {baseline_sha}")
    print(f"Upstream {ref}: {upstream_sha}")
    if upstream_sha == baseline_sha:
        print("Core upstream freshness: PASS")
        return 0

    if comparison:
        status = comparison.get("status", "unknown")
        ahead = comparison.get("ahead_by")
        behind = comparison.get("behind_by")
        if status in {"ahead", "identical"} and isinstance(ahead, int):
            print(f"Core upstream freshness: STALE ({ahead} upstream commit(s) ahead)")
        else:
            details = []
            if status:
                details.append(f"status={status}")
            if isinstance(ahead, int):
                details.append(f"ahead_by={ahead}")
            if isinstance(behind, int):
                details.append(f"behind_by={behind}")
            print("Core upstream freshness: DIVERGED" + (f" ({', '.join(details)})" if details else ""))
    else:
        print("Core upstream freshness: STALE")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether a consumer's recorded Project Forge Core commit is current upstream.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Consumer repository root")
    parser.add_argument("--ref", default="main", help="Core ref to compare against (default: main)")
    parser.add_argument(
        "--token-env",
        default="PROJECT_FORGE_CORE_READ_TOKEN",
        help="Environment variable containing a GitHub token for private Core access",
    )
    parser.add_argument("--core-path", type=Path, help="Use a local Core checkout instead of GitHub API")
    parser.add_argument(
        "--skip-if-unavailable",
        action="store_true",
        help="Exit successfully if upstream cannot be queried (useful when CI token is not configured)",
    )
    args = parser.parse_args()

    token = os.getenv(args.token_env) or os.getenv("GITHUB_TOKEN")
    return check_upstream(
        args.root,
        ref=args.ref,
        token=token,
        core_path=args.core_path,
        skip_if_unavailable=args.skip_if_unavailable,
    )


if __name__ == "__main__":
    raise SystemExit(main())
