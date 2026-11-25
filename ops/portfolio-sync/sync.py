#!/usr/bin/env python3
"""Add newly open GitHub Issues to one private GitHub Projects v2 board.

No database. No issue modification. No field rewrites. No release triggers.
Runs via an isolated Linux user and the GitHub CLI account authorization.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

CONFIG_PATH = Path(os.environ.get('PF_PORTFOLIO_CONFIG', '/etc/project-forge-portfolio-sync/config.json'))
LOCK_PATH = Path(os.environ.get('PF_PORTFOLIO_LOCK', '/var/lib/project-forge-portfolio-sync/sync.lock'))
MAX_PROJECT_ITEMS = 5000
MAX_REPO_ISSUES = 1000
URL_PATTERN = re.compile(r'^https://github\.com/(?P<owner>[A-Za-z0-9-]+)/(?P<repo>[A-Za-z0-9_.-]+)/issues/(?P<number>[1-9][0-9]*)$')

class SyncError(Exception):
    pass


def gh(*args: str) -> str:
    env = dict(os.environ, GH_PROMPT_DISABLED='1', GH_PAGER='cat', PAGER='cat')
    if env.get('GITHUB_TOKEN') or env.get('GH_TOKEN'):
        raise SyncError('Refusing inherited GH_TOKEN/GITHUB_TOKEN; use the dedicated service account gh login')
    try:
        result = subprocess.run(['gh', *args], capture_output=True, text=True,
                                check=False, timeout=120, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SyncError(f'GitHub CLI unavailable or timed out ({type(exc).__name__})') from exc
    if result.returncode:
        # Do not emit raw GitHub error payloads into systemd logs.
        raise SyncError(f'gh {" ".join(args[:2])} failed (exit {result.returncode}); check auth/access/network')
    return result.stdout


def gh_json(*args: str):
    try:
        return json.loads(gh(*args))
    except (ValueError, TypeError) as exc:
        raise SyncError('GitHub returned invalid JSON; no updates made') from exc


def settings(path: Path) -> dict:
    try:
        obj = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise SyncError(f'Cannot load JSON configuration: {path}') from exc
    if not isinstance(obj, dict):
        raise SyncError('Configuration must be an object')
    if not (isinstance(obj.get('owner'), str) and re.fullmatch(r'[A-Za-z0-9-]{1,39}', obj['owner'])):
        raise SyncError('Invalid owner')
    if not (isinstance(obj.get('project_number'), int) and obj['project_number'] > 0):
        raise SyncError('Invalid project_number')
    if not (isinstance(obj.get('project_name'), str) and obj['project_name'].strip()):
        raise SyncError('Invalid project_name')
    repos = obj.get('repositories')
    if not isinstance(repos, list) or not repos or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9-]+/[A-Za-z0-9_.-]+', v) for v in repos) or len(set(repos)) != len(repos):
        raise SyncError('Invalid or duplicate repositories')
    if any(not r.startswith(obj['owner'] + '/') for r in repos):
        raise SyncError('All repositories must be owned by configured user')
    skip = obj.get('exclude_title_prefixes', [])
    if not isinstance(skip, list) or any(not isinstance(x, str) or not x for x in skip):
        raise SyncError('Invalid exclude_title_prefixes')
    return obj


def verify_project(cfg: dict) -> dict:
    login = gh('api', 'user', '--jq', '.login').strip()
    if login != cfg['owner']:
        raise SyncError(f'GitHub identity mismatch: expected {cfg["owner"]}; got {login or "unknown"}')
    query = '''query($login: String!, $number: Int!) {
      user(login: $login) {
        projectV2(number: $number) {
          id title number url public
          repositories(first: 100) { nodes { nameWithOwner } pageInfo { hasNextPage } }
        }
      }
    }'''
    obj = gh_json('api', 'graphql', '-f', f'query={query}', '-f', f'login={cfg["owner"]}',
                  '-F', f'number={cfg["project_number"]}')
    p = (obj.get('data') or {}).get('user') or {}
    p = p.get('projectV2') or {}
    if p.get('public') is not False:
        raise SyncError('Project visibility is not verified PRIVATE; refusing writes')
    if p.get('title') != cfg['project_name'] or p.get('number') != cfg['project_number']:
        raise SyncError('Project title/number mismatch; refusing writes')
    repos = p.get('repositories') or {}
    if (repos.get('pageInfo') or {}).get('hasNextPage'):
        raise SyncError('More than 100 linked repositories; refusing incomplete verification')
    linked = {x['nameWithOwner'] for x in repos.get('nodes', []) if isinstance(x, dict) and isinstance(x.get('nameWithOwner'), str)}
    missing = set(cfg['repositories']) - linked
    if missing:
        raise SyncError(f'Missing linked repos: {", ".join(sorted(missing))}')
    if p.get('url') != f'https://github.com/users/{cfg["owner"]}/projects/{cfg["project_number"]}':
        raise SyncError('Project URL mismatch')
    return p


def issue_url(url: str, repos: set[str]) -> bool:
    m = URL_PATTERN.fullmatch(url)
    return bool(m and f'{m.group("owner")}/{m.group("repo")}' in repos)


def fetch_existing(cfg: dict) -> set[str]:
    obj = gh_json('project', 'item-list', str(cfg['project_number']), '--owner', cfg['owner'],
                  '--limit', str(MAX_PROJECT_ITEMS), '--format', 'json')
    if not isinstance(obj, dict) or not isinstance(obj.get('items'), list):
        raise SyncError('Project item response incomplete')
    items = obj['items']
    total = obj.get('totalCount')
    if len(items) >= MAX_PROJECT_ITEMS or (isinstance(total, int) and total > len(items)):
        raise SyncError('Project item pagination incomplete; refusing potential duplicates')
    # Content URLs may include PRs/drafts; only issue URLs matter for deduplication.
    found = set()
    for item in items:
        if not isinstance(item, dict):
            raise SyncError('Unexpected Project item structure')
        content = item.get('content') or {}
        url = content.get('url') if isinstance(content, dict) else None
        if isinstance(url, str) and URL_PATTERN.fullmatch(url):
            found.add(url)
    return found


def fetch_candidates(cfg: dict) -> list[str]:
    out: list[str] = []
    repo_set = set(cfg['repositories'])
    for repo in cfg['repositories']:
        obj = gh_json('issue', 'list', '--repo', repo, '--state', 'open',
                      '--limit', str(MAX_REPO_ISSUES), '--json', 'url,title')
        if not isinstance(obj, list):
            raise SyncError(f'Invalid Issue listing for {repo}')
        if len(obj) >= MAX_REPO_ISSUES:
            raise SyncError(f'Issue list may be truncated for {repo}; refusing partial sync')
        for entry in obj:
            if not isinstance(entry, dict) or not isinstance(entry.get('title'), str) or not isinstance(entry.get('url'), str):
                raise SyncError(f'Malformed Issue listing for {repo}')
            url, title = entry['url'], entry['title']
            if not issue_url(url, repo_set) or f'{URL_PATTERN.fullmatch(url).group("owner")}/{URL_PATTERN.fullmatch(url).group("repo")}' != repo:
                raise SyncError(f'Unexpected Issue URL from {repo}; refusing unsafe sync')
            if any(title.startswith(prefix) for prefix in cfg.get('exclude_title_prefixes', [])):
                continue
            out.append(url)
    return list(dict.fromkeys(out))


def synchronize(cfg: dict, dry_run: bool = False) -> dict:
    p = verify_project(cfg)
    current = fetch_existing(cfg)
    candidates = fetch_candidates(cfg)  # Acquire all sources *before* changing the Project.
    missing = [url for url in candidates if url not in current]
    failures = []
    added = 0
    if not dry_run:
        for url in missing:
            try:
                gh('project', 'item-add', str(cfg['project_number']), '--owner', cfg['owner'], '--url', url)
            except SyncError:
                failures.append(url)
            else:
                added += 1
    result = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'project': p['url'], 'repositories_checked': len(cfg['repositories']),
        'existing_items': len(current), 'open_candidates': len(candidates),
        'already_present': len(candidates) - len(missing), 'missing': len(missing),
        'added': added, 'failures': failures, 'dry_run': dry_run,
    }
    if failures:
        raise SyncError(f'{len(failures)} add(s) failed; retry next run. Result: {json.dumps(result)}')
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Sync open GitHub Issues to private Project Forge Portfolio')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--once', action='store_true', help='Reconcile missing issues')
    group.add_argument('--dry-run', action='store_true', help='Read only, report missing issues')
    group.add_argument('--check', action='store_true', help='Check GitHub identity, Project privacy and repo links')
    args = parser.parse_args(argv)
    try:
        cfg = settings(CONFIG_PATH)
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOCK_PATH.open('a+') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(json.dumps({'status':'skipped', 'reason':'run already active'}), flush=True)
                return 0
            if args.check:
                p = verify_project(cfg)
                print(json.dumps({'status':'ok', 'project':p['url'], 'private':True,
                                  'repositories_linked':len(cfg['repositories'])}), flush=True)
            else:
                print(json.dumps(synchronize(cfg, dry_run=args.dry_run)), flush=True)
    except SyncError as exc:
        print(f'ERROR: {exc}', file=sys.stderr, flush=True)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
