"""CLI for loopback-only workstation application deployment."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .errors import DeploymentKitError
from .local_runtime import (
    PRODUCTION_APP_DEPLOY_WRITE_PHRASE,
    apply_local_deploy,
    local_deploy_write_phrase,
    local_inventory,
    plan_local_deploy,
)
from .local_spec import normalize_workstation_spec
from .local_sqlite import ensure_local_sqlite, local_sqlite_status


LOCAL_SQLITE_ENSURE_WRITE_PHRASE = "[LOCAL SQLITE ENSURE]"


def _print(value: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True))
    elif isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: {json.dumps(item, sort_keys=True) if isinstance(item, (dict, list)) else item}")
    else:
        print(value)


def _parse_env(items: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for item in items:
        if "=" not in item:
            raise DeploymentKitError("--env entries must use NAME=value form.")
        key, value = item.split("=", 1)
        result.append((key, value))
    return result


def _parse_mapping(value: str) -> dict[str, int]:
    try:
        left, right = value.split(":")
        return {"hostPort": int(left), "runtimePort": int(right)}
    except (ValueError, TypeError) as error:
        raise DeploymentKitError("--additional-port requires HOST_PORT:RUNTIME_PORT.") from error


def _parse_mount(value: str) -> dict[str, str]:
    try:
        left, right = value.split("::", 1)
        if not left or not right:
            raise ValueError("empty path")
        return {"source": left, "target": right}
    except ValueError as error:
        raise DeploymentKitError("--read-only-mount requires SOURCE::TARGET.") from error


def _confirm(args: argparse.Namespace, phrase: str, action: str) -> None:
    if args.yes:
        return
    entered = input(f"Type {phrase} to {action}: ").strip()
    if entered != phrase:
        raise DeploymentKitError(f"{action.capitalize()} was not authorized.")


def _add_sqlite_identity(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--owner-repo", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--app-slug", required=True)
    parser.add_argument("--database-file", required=True)
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-forge-deploy local")
    sub = parser.add_subparsers(dest="command", required=True)

    inventory = sub.add_parser(
        "inventory",
        help="Read Project Forge-owned workstation application runtime evidence without writes",
    )
    inventory.add_argument("--json", action="store_true")

    sqlite_status = sub.add_parser(
        "sqlite-status",
        help="Inspect one Project Forge-owned workstation SQLite database without writes",
    )
    _add_sqlite_identity(sqlite_status)

    sqlite_ensure = sub.add_parser(
        "sqlite-ensure",
        help="Create a missing Project Forge-owned workstation SQLite database non-destructively",
    )
    _add_sqlite_identity(sqlite_ensure)
    sqlite_ensure.add_argument("--yes", action="store_true")

    deploy = sub.add_parser(
        "deploy",
        help="Deploy one immutable application container bound only to loopback",
    )
    deploy.add_argument("--owner-repo", required=True)
    deploy.add_argument("--environment", required=True)
    deploy.add_argument(
        "--production",
        action="store_true",
        help="Classify this named environment as Production even when its name is not literally 'production'",
    )
    deploy.add_argument("--app-slug", required=True)
    deploy.add_argument("--container-name", required=True)
    deploy.add_argument("--image", required=True)
    deploy.add_argument("--runtime-port", type=int, required=True)
    deploy.add_argument("--host-port", type=int, required=True)
    deploy.add_argument("--health-path", required=True)
    deploy.add_argument("--run-as", required=True)
    deploy.add_argument("--persistence-mode", choices=("none", "directory"), required=True)
    deploy.add_argument("--data-container-path")
    deploy.add_argument("--env", action="append", default=[])
    deploy.add_argument("--additional-port", action="append", default=[], metavar="HOST_PORT:RUNTIME_PORT")
    deploy.add_argument("--read-only-mount", action="append", default=[], metavar="SOURCE::TARGET")
    deploy.add_argument("--json", action="store_true")
    deploy.add_argument("--yes", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inventory":
            _print(local_inventory(), as_json=args.json)
            return 0

        if args.command == "sqlite-status":
            _print(
                local_sqlite_status(
                    owner_repo=args.owner_repo,
                    environment=args.environment,
                    app_slug=args.app_slug,
                    database_file=args.database_file,
                ),
                as_json=args.json,
            )
            return 0

        if args.command == "sqlite-ensure":
            status = local_sqlite_status(
                owner_repo=args.owner_repo,
                environment=args.environment,
                app_slug=args.app_slug,
                database_file=args.database_file,
            )
            if status["state"] == "ready":
                _print(status, as_json=args.json)
                return 0
            if status["state"] == "unmanaged-existing":
                raise DeploymentKitError(
                    "Refusing automatic adoption of an existing unmanaged local SQLite database."
                )
            _print(status, as_json=False)
            _confirm(
                args,
                LOCAL_SQLITE_ENSURE_WRITE_PHRASE,
                f"create local SQLite storage for {args.app_slug} ({args.environment})",
            )
            _print(
                ensure_local_sqlite(
                    owner_repo=args.owner_repo,
                    environment=args.environment,
                    app_slug=args.app_slug,
                    database_file=args.database_file,
                ),
                as_json=args.json,
            )
            return 0

        spec = normalize_workstation_spec(
            owner_repo=args.owner_repo,
            environment=args.environment,
            app_slug=args.app_slug,
            container_name=args.container_name,
            image=args.image,
            runtime_port=args.runtime_port,
            host_port=args.host_port,
            health_path=args.health_path,
            run_as=args.run_as,
            persistence_mode=args.persistence_mode,
            data_container_path=args.data_container_path,
            environment_variables=_parse_env(args.env),
            additional_port_bindings=[_parse_mapping(value) for value in args.additional_port],
            read_only_mounts=[_parse_mount(value) for value in args.read_only_mount],
        )
        plan = plan_local_deploy(spec)
        production_classified = args.production or plan["environment"] == "production"
        plan_view = {key: value for key, value in plan.items() if key != "spec"}
        plan_view["productionClassified"] = production_classified
        _print(plan_view, as_json=False)
        phrase = PRODUCTION_APP_DEPLOY_WRITE_PHRASE if production_classified else local_deploy_write_phrase(plan)
        _confirm(
            args,
            phrase,
            f"deploy {plan['appSlug']} ({plan['environment']}) on this workstation",
        )
        _print(apply_local_deploy(plan), as_json=args.json)
        return 0
    except DeploymentKitError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
