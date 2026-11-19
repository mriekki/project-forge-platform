#!/usr/bin/env python3
"""Validate a reviewed, application-owned Release Notes v1 manifest.

This does not grant human content approval or verified Production activation.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'contract/release-manifest.schema.json').read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


class ManifestValidationError(ValueError):
    pass


def strict_json(path: Path) -> Any:
    def pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ManifestValidationError('Duplicated JSON field.')
            result[key] = value
        return result
    try:
        if path.stat().st_size > 128 * 1024:
            raise ManifestValidationError('Manifest exceeds the approved size limit.')
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs_no_duplicates)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ManifestValidationError('Manifest is not valid UTF-8 JSON.') from error


def validate(data: Any, previous: Any | None = None) -> dict[str, Any]:
    violations = list(VALIDATOR.iter_errors(data))
    if violations:
        raise ManifestValidationError(f'Manifest schema invalid at {list(violations[0].path)}.')
    seen = set()
    for item in data['entries']:
        if item['announcementId'] in seen:
            raise ManifestValidationError('Duplicate announcementId.')
        seen.add(item['announcementId'])
        for key in ('title', 'summary', 'details'):
            if key not in item:
                continue
            text = item[key]
            if text != text.strip() or any(ord(char) < 32 and (key != 'details' or char != '\n') for char in text):
                raise ManifestValidationError('Invalid whitespace or controls in user-facing text.')
            if key != 'details' and '\n' in text:
                raise ManifestValidationError('Only details may contain newlines.')
            if ('<' in text or '>' in text or 'NEEDS HUMAN DESCRIPTION' in text.upper() or
                    re.search(r'https?://|www\.|\]\(|!\[', text, flags=re.IGNORECASE)):
                raise ManifestValidationError('Unreviewed HTML, URL, Markdown or placeholder in user text.')
    if previous is not None:
        validate(previous)
        old = {item['announcementId']: item for item in previous['entries']}
        for current in data['entries']:
            prior = old.get(current['announcementId'])
            if prior is None:
                if current['revision'] != 1:
                    raise ManifestValidationError('New announcement ID must begin at revision 1.')
                continue
            changed = {k:v for k,v in current.items() if k != 'revision'} != {
                k:v for k,v in prior.items() if k != 'revision'
            }
            if changed and current['revision'] <= prior['revision']:
                raise ManifestValidationError('Correction must retain ID and increment revision.')
            if not changed and current['revision'] != prior['revision']:
                raise ManifestValidationError('Unchanged notes must retain revision.')
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--previous', type=Path)
    args = parser.parse_args()
    try:
        current = strict_json(args.manifest)
        previous = strict_json(args.previous) if args.previous else None
        result = validate(current, previous)
        print(f"SCHEMA VALID: {len(result['entries'])} entries. Editorial and Production verification still required.")
        return 0
    except (ManifestValidationError, OSError) as error:
        print(f'REJECTED: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
