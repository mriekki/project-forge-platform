"""CLI for strict target-access diagnosis."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

from .access_diagnosis import diagnose_target_access, guided_access_report
from .errors import DeploymentKitError


def _print(value: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                print(f"{key}: {json.dumps(item, sort_keys=True)}")
            else:
                print(f"{key}: {item}")
        return
    print(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="project-forge-deploy access",
        description="Read-only strict SSH target-access diagnosis.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    diagnose = subparsers.add_parser(
        "diagnose",
        help="Diagnose one configured target without mutating target or workstation state",
    )
    diagnose.add_argument("name")
    diagnose.add_argument(
        "--address",
        help=(
            "Exact temporary IPv4/IPv6 address independently confirmed by the operator. "
            "Used only for this read-only diagnosis and never persisted."
        ),
    )
    diagnose.add_argument("--json", action="store_true")
    diagnose.add_argument("--guided", action="store_true",
                          help="Show sanitized stage guidance and read-only console handoff")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "diagnose":
            result = diagnose_target_access(args.name, temporary_address=args.address)
            if args.guided:
                result = guided_access_report(result)
            _print(result, as_json=args.json)
            return 0 if result.get("state") == "verified" else 2
        raise DeploymentKitError("Unsupported access command.")
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError) as error:
        if args.command != "diagnose" or not args.guided:
            raise
        print("ERROR: Guided diagnosis unavailable. Check the existing target profile and local prerequisites; inspect details privately.", file=sys.stderr)
        return 2
    except DeploymentKitError as error:
        if args.command == "diagnose" and args.guided:
            print("ERROR: Guided diagnosis unavailable. Check the existing target profile and local prerequisites; inspect details privately.", file=sys.stderr)
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
