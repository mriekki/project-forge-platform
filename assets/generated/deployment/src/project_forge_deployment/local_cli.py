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
    if getattr(args, "yes", False):
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


def _add_https_identity(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--owner-repo", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--app-slug", required=True)


def _add_https_spec(parser: argparse.ArgumentParser) -> None:
    _add_https_identity(parser)
    parser.add_argument("--image", required=True)
    parser.add_argument("--runtime-port", type=int, default=8080)
    parser.add_argument("--health-path", default="/api/auth/me")
    parser.add_argument("--run-as", default="1654:1654")
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("--read-only-mount", action="append", default=[], metavar="SOURCE::TARGET")


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

    https = sub.add_parser(
        "https",
        help="Opt-in WSL2 localhost HTTPS ingress for one Auth Kit workstation application",
    )
    https_actions = https.add_subparsers(dest="https_command", required=True)
    https_status = https_actions.add_parser("status", help="Inspect local Auth HTTPS resources and trust state")
    _add_https_identity(https_status)
    https_status.add_argument("--json", action="store_true")
    https_plan = https_actions.add_parser("plan", help="Create a read-only local Auth HTTPS deployment plan")
    _add_https_spec(https_plan)
    https_plan.add_argument("--json", action="store_true")
    https_apply = https_actions.add_parser("apply", help="Apply a reviewed local Auth HTTPS plan")
    _add_https_spec(https_apply)
    https_apply.add_argument("--json", action="store_true")
    trust_status = https_actions.add_parser("trust-status", help="Inspect the exact Windows CurrentUser CA root")
    _add_https_identity(trust_status)
    trust_status.add_argument("--json", action="store_true")
    trust_install = https_actions.add_parser("trust-install", help="Install the app-scoped CA root after authorization")
    _add_https_identity(trust_install)
    trust_install.add_argument("--json", action="store_true")
    trust_remove = https_actions.add_parser("trust-remove", help="Remove only the exact recorded CA thumbprint")
    _add_https_identity(trust_remove)
    trust_remove.add_argument("--thumbprint", required=True)
    trust_remove.add_argument("--json", action="store_true")
    https_remove = https_actions.add_parser("remove", help="Stop the app and remove its exact HTTPS resources")
    _add_https_identity(https_remove)
    https_remove.add_argument("--json", action="store_true")
    https_recover = https_actions.add_parser("recover", help="Clean an exact partial or blocked HTTPS lifecycle")
    _add_https_identity(https_recover)
    https_recover.add_argument("--json", action="store_true")
    return parser


def _local_https_main(args: argparse.Namespace) -> int:
    from . import local_https_auth

    identity = {
        "owner_repo": args.owner_repo,
        "app_slug": args.app_slug,
        "environment": args.environment,
    }
    if args.https_command == "status":
        _print(local_https_auth.local_https_auth_status_for_identity(**identity), as_json=args.json)
        return 0
    if args.https_command == "trust-status":
        _print(local_https_auth.local_https_auth_trust_status({
            "ownerRepo": args.owner_repo,
            "appSlug": args.app_slug,
            "environment": args.environment,
        }), as_json=args.json)
        return 0
    if args.https_command == "trust-install":
        trust = local_https_auth.local_https_auth_trust_status({
            "ownerRepo": args.owner_repo,
            "appSlug": args.app_slug,
            "environment": args.environment,
        })
        _print(trust, as_json=args.json)
        if trust["state"] != "not-installed" or trust.get("certificateState") != "valid":
            raise DeploymentKitError(
                "The local HTTPS Auth trust root is not in an installable state; inspect the exact thumbprint first."
            )
        _confirm(
            args,
            local_https_auth.LOCAL_HTTPS_AUTH_TRUST_WRITE_PHRASE,
            f"install the local HTTPS Auth CA root for {args.app_slug} ({args.environment})",
        )
        _print(
            local_https_auth.install_local_https_auth_trust({
                "ownerRepo": args.owner_repo,
                "appSlug": args.app_slug,
                "environment": args.environment,
            }),
            as_json=args.json,
        )
        return 0
    if args.https_command == "trust-remove":
        trust = local_https_auth.local_https_auth_trust_status({
            "ownerRepo": args.owner_repo,
            "appSlug": args.app_slug,
            "environment": args.environment,
        })
        _print(trust, as_json=args.json)
        _confirm(
            args,
            local_https_auth.LOCAL_HTTPS_AUTH_TRUST_REMOVE_PHRASE,
            f"remove the exact local HTTPS Auth CA thumbprint for {args.app_slug} ({args.environment})",
        )
        _print(
            local_https_auth.remove_local_https_auth_trust(
                {
                    "ownerRepo": args.owner_repo,
                    "appSlug": args.app_slug,
                    "environment": args.environment,
                },
                args.thumbprint,
            ),
            as_json=args.json,
        )
        return 0
    if args.https_command == "remove":
        status = local_https_auth.local_https_auth_status_for_identity(**identity)
        _print(status, as_json=args.json)
        if status["state"] != "ready":
            raise DeploymentKitError("Only a ready, drift-free local HTTPS Auth runtime can be removed.")
        if status.get("trust", {}).get("state") != "not-installed":
            raise DeploymentKitError(
                "Remove the exact CurrentUser CA thumbprint in a separate authorized operation before runtime teardown."
            )
        _confirm(
            args,
            local_https_auth.LOCAL_HTTPS_AUTH_REMOVE_PHRASE,
            f"remove the local HTTPS Auth runtime for {args.app_slug} ({args.environment})",
        )
        _print(
            local_https_auth.remove_local_https_auth({
                "ownerRepo": args.owner_repo,
                "appSlug": args.app_slug,
                "environment": args.environment,
            }),
            as_json=args.json,
        )
        return 0
    if args.https_command == "recover":
        _confirm(
            args,
            local_https_auth.LOCAL_HTTPS_AUTH_RECOVER_PHRASE,
            f"recover the partial local HTTPS Auth runtime for {args.app_slug} ({args.environment})",
        )
        _print(
            local_https_auth.recover_local_https_auth({
                "ownerRepo": args.owner_repo,
                "appSlug": args.app_slug,
                "environment": args.environment,
            }),
            as_json=args.json,
        )
        return 0

    spec = local_https_auth.normalize_local_https_auth_spec(
        owner_repo=args.owner_repo,
        environment=args.environment,
        app_slug=args.app_slug,
        image=args.image,
        runtime_port=args.runtime_port,
        health_path=args.health_path,
        run_as=args.run_as,
        environment_variables=_parse_env(args.env),
        read_only_mounts=[_parse_mount(value) for value in args.read_only_mount],
    )
    plan = local_https_auth.plan_local_https_auth(spec)
    plan_view = {key: value for key, value in plan.items() if key not in {"spec", "inventorySnapshot", "materialSnapshot"}}
    _print(plan_view, as_json=args.json)
    if args.https_command == "plan":
        return 0
    _confirm(
        args,
        local_https_auth.LOCAL_HTTPS_AUTH_DEPLOY_WRITE_PHRASE,
        f"deploy the local HTTPS Auth runtime for {args.app_slug} ({args.environment})",
    )
    _print(local_https_auth.apply_local_https_auth(plan), as_json=args.json)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "https":
            return _local_https_main(args)

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
