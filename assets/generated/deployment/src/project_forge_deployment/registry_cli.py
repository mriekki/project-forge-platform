"""CLI for read-only registry capability verification."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .errors import DeploymentKitError
from .registry_access import (
    RegistryCapabilityError,
    verify_registry_access,
    verify_workstation_registry_access,
)


def _print(value: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: {item}")
        return
    print(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-forge-deploy registry")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser(
        "verify",
        help=(
            "Verify exact-image registry manifest access on the named remote target without pulling "
            "or modifying target state"
        ),
    )
    verify.add_argument("name", help="Named remote target profile")
    verify.add_argument("--image", required=True)
    verify.add_argument("--json", action="store_true")

    verify_workstation = sub.add_parser(
        "verify-workstation",
        help=(
            "Verify exact-image registry manifest access from this workstation without pulling "
            "or modifying target state"
        ),
    )
    verify_workstation.add_argument("--image", required=True)
    verify_workstation.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "verify":
            _print(
                verify_registry_access(args.name, args.image),
                as_json=args.json,
            )
            return 0
        if args.command == "verify-workstation":
            _print(
                verify_workstation_registry_access(args.image),
                as_json=args.json,
            )
            return 0
    except RegistryCapabilityError as error:
        if getattr(args, "json", False):
            _print(error.result, as_json=True)
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except DeploymentKitError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 2
