#!/usr/bin/env python3
"""Verify first native stable migration changes only approved version metadata.

Reads archive entries without extraction. Independent receipt/registry/source
verification and exact publishing authorization remain separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile

PACKAGE = "@mriekki/project-forge"
PREVIOUS = "4.35.0"
TARGET = "4.36.0"
METADATA = ("package.json", "assets/components.json", "assets/generated/ASSEMBLY.json")
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_CONTENT = 128 * 1024 * 1024
MAX_FILES = 10000


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha256(path):
    need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= MAX_ARCHIVE,
         "Invalid archive input")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_files(path):
    files, seen = {}, set()
    total = 0
    with tarfile.open(path, "r:gz") as archive:
        for entry in archive:
            name = entry.name
            parts = name.split("/")
            need(parts[0] == "package" and
                 all(p not in ("", ".", "..") for p in parts) and
                 "\\" not in name and "\x00" not in name and
                 name.casefold() not in seen, "Unsafe or duplicate archive entry")
            seen.add(name.casefold())
            need(len(seen) <= MAX_FILES, "Too many archive entries")
            if entry.isdir():
                continue
            need(entry.isfile() and len(parts) > 1 and not entry.issparse(),
                 "Unsupported archive entry type")
            total += entry.size
            need(0 <= entry.size and total <= MAX_CONTENT, "Archive content exceeds bound")
            with archive.extractfile(entry) as stream:
                value = stream.read(entry.size + 1)
            need(len(value) == entry.size, "Truncated archive entry")
            files["/".join(parts[1:])] = (entry.mode & 0o777, value)
    return files


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "Duplicate metadata key")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError("Invalid JSON constant")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid_constant)


def compare(prior, candidate, prior_sha256):
    need(isinstance(prior_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", prior_sha256),
         "Exact prior archive SHA-256 required")
    need(sha256(prior) == prior_sha256, "Prior archive digest mismatch")
    candidate_sha = sha256(candidate)
    old, new = read_files(prior), read_files(candidate)
    need(set(old) == set(new) and all(name in old for name in METADATA),
         "Archive inventory differs")
    for name, (mode, content) in old.items():
        new_mode, new_content = new[name]
        need(mode == new_mode, "Archive file mode differs")
        if name not in METADATA:
            need(content == new_content, "Non-version package content differs")
            continue
        before, after = strict_json(content), strict_json(new_content)
        need(isinstance(before, dict) and isinstance(after, dict) and
             before.get("version") == PREVIOUS and after.get("version") == TARGET,
             "Metadata version differs")
        if name == "package.json":
            need(before.get("name") == PACKAGE and
                 ("private" not in before or before["private"] is False) and
                 before.get("publishConfig") == {"access": "public", "provenance": True},
                 "Unexpected prior public package identity")
        else:
            need(type(before.get("schemaVersion")) is int and before["schemaVersion"] == 2 and
                 before.get("package") == PACKAGE, "Unexpected prior assembly identity")
        before["version"] = TARGET
        # Canonical type-sensitive JSON comparison, not Python bool/int equality.
        need(json.dumps(before, sort_keys=True, ensure_ascii=False) ==
             json.dumps(after, sort_keys=True, ensure_ascii=False),
             "Unapproved metadata change")
    need(sha256(prior) == prior_sha256 and sha256(candidate) == candidate_sha,
         "Archive changed during comparison")
    return {"result": "FIRST_NATIVE_STABLE_CONTENT_MATCH",
            "previousVersion": PREVIOUS, "candidateVersion": TARGET,
            "candidateSha256": candidate_sha, "fileCount": len(old),
            "releaseAuthorized": False, "published": False,
            "sourceOwnershipTransferred": False, "productionAuthorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--prior-sha256", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(compare(args.prior, args.candidate, args.prior_sha256), sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, tarfile.TarError):
        print("First native stable content comparison refused", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
