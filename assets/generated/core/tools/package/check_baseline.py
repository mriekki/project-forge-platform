#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

BASELINE_FILENAME = "CORE_BASELINE.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_managed_path(root: Path, rel: str) -> Path:
    candidate = Path(rel)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"unsafe managed path: {rel}")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"managed path escapes repository root: {rel}") from exc
    return resolved


def verify(root: Path, baseline_path: Path | None = None) -> int:
    root = root.resolve()
    baseline_path = baseline_path.resolve() if baseline_path else root / BASELINE_FILENAME
    if not baseline_path.is_file():
        print(f"MISSING baseline: {baseline_path}")
        return 2

    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"INVALID baseline JSON: {exc}")
        return 2

    if baseline.get("schemaVersion") != 1:
        print(f"UNSUPPORTED baseline schemaVersion: {baseline.get('schemaVersion')}")
        return 2

    managed = baseline.get("managedPaths")
    if not isinstance(managed, list) or not managed:
        print("INVALID baseline: managedPaths is missing or empty")
        return 2

    failures = 0
    seen: set[str] = set()
    for item in managed:
        rel = item.get("path")
        expected = item.get("sha256")
        if not rel or not expected:
            print(f"INVALID managed path entry: {item!r}")
            failures += 1
            continue
        if rel in seen:
            print(f"INVALID duplicate managed path: {rel}")
            failures += 1
            continue
        seen.add(rel)
        try:
            path = resolve_managed_path(root, rel)
        except ValueError as exc:
            print(f"INVALID {exc}")
            failures += 1
            continue
        if not path.is_file():
            print(f"MISSING {rel}")
            failures += 1
            continue
        actual = sha256_file(path)
        if actual != expected:
            print(f"DRIFT   {rel}")
            failures += 1
        else:
            print(f"SAME    {rel}")

    print()
    if failures:
        print(f"Core baseline integrity: FAIL ({failures} path(s))")
        return 1
    print(f"Core baseline integrity: PASS ({len(managed)} managed path(s))")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a consumer's Core-managed paths against CORE_BASELINE.json.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Consumer repository root")
    parser.add_argument("--baseline", type=Path, help="Optional explicit baseline file")
    args = parser.parse_args()
    return verify(args.root, args.baseline)


if __name__ == "__main__":
    raise SystemExit(main())
