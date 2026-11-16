"""CLI for deterministic project-owned deployment topology binding."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .errors import DeploymentKitError
from .project_topology import apply_environment_binding, plan_environment_binding


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


def _confirm(args: argparse.Namespace, phrase: str, action: str) -> None:
    if args.yes:
        return
    entered = input(f"Type {phrase} to {action}: ").strip()
    if entered != phrase:
        raise DeploymentKitError(f"{action.capitalize()} was not authorized.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-forge-deploy topology")
    sub = parser.add_subparsers(dest="command", required=True)

    for command in ("plan-binding", "bind"):
        item = sub.add_parser(
            command,
            help=(
                "Preview completion of one deferred remote-target binding"
                if command == "plan-binding"
                else "Persist one reviewed deferred remote-target binding"
            ),
        )
        item.add_argument("environment")
        item.add_argument("--target-profile", required=True)
        item.add_argument("--root", type=Path, default=Path("."))
        item.add_argument("--json", action="store_true")
        if command == "bind":
            item.add_argument("--yes", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan = plan_environment_binding(args.root, args.environment, args.target_profile)
        if args.command == "plan-binding":
            _print(plan, as_json=args.json)
            return 0
        if plan["status"] == "already-bound":
            _print(plan, as_json=args.json)
            return 0
        if not args.json:
            _print(plan, as_json=False)
        _confirm(
            args,
            plan["requiredAuthorization"],
            f"bind project environment {args.environment} to target profile {args.target_profile}",
        )
        result = apply_environment_binding(plan)
        _print(result, as_json=args.json)
        return 0
    except DeploymentKitError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
