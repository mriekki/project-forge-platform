"""CLI for optional public-ingress providers."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from .cloudflare_ingress import (
    AUTHENTICATED_ORIGIN_CHANGE_FREEZE_PHRASE,
    AUTHENTICATED_ORIGIN_MIGRATION_PHRASE,
    CLOUDFLARE_API_TOKEN_ENV,
    HOST_PUBLIC_INGRESS_WRITE_PHRASE,
    PUBLIC_INGRESS_ROUTE_REMOVE_PHRASE,
    PUBLIC_INGRESS_ROUTE_WRITE_PHRASE,
    apply_authenticated_origin_migration,
    apply_cloudflare_ingress,
    cloudflare_ingress_doctor,
    cloudflare_ingress_status,
    cloudflare_route_inventory,
    plan_authenticated_origin_migration,
    plan_cloudflare_ingress,
    plan_public_route,
    plan_public_route_removal,
)
from .cloudflare_route_apply import apply_public_route, apply_public_route_removal
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


def _token() -> str:
    value = os.environ.get(CLOUDFLARE_API_TOKEN_ENV, "")
    if not value.strip():
        raise DeploymentKitError(
            f"Cloudflare API authorization is not available. Set {CLOUDFLARE_API_TOKEN_ENV} "
            "in the current workstation process/secret boundary; never put the token in the Project repository or command line."
        )
    return value.strip()


def _confirm(args: argparse.Namespace, phrase: str, action: str) -> None:
    if getattr(args, "yes", False):
        return
    entered = input(f"Type {phrase} to {action}: ").strip()
    if entered != phrase:
        raise DeploymentKitError(f"{action.capitalize()} was not authorized.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-forge-deploy ingress")
    providers = parser.add_subparsers(dest="provider", required=True)
    cloudflare = providers.add_parser("cloudflare", help="Cloudflare Tunnel public ingress")
    commands = cloudflare.add_subparsers(dest="command", required=True)

    for command in ("status", "doctor"):
        item = commands.add_parser(command, help=f"Read Cloudflare ingress {command} without writes")
        item.add_argument("name", help="Logical Project Forge target profile")
        item.add_argument("--scope", required=True, help="Shared ingress scope, for example production")
        item.add_argument("--json", action="store_true")

    configure = commands.add_parser(
        "configure",
        help="Create/adopt one remotely managed tunnel and install the shared cloudflared runtime",
    )
    configure.add_argument("name")
    configure.add_argument("--scope", required=True)
    configure.add_argument("--zone", required=True, help="Existing active Cloudflare zone, for example example.com")
    configure.add_argument("--tunnel-name", help="Optional explicit tunnel name; default is project-forge-<scope>")
    configure.add_argument("--authenticated-origin", action="store_true", help="Experimental: isolate the public connector origin on a private Unix socket; only new scopes")
    configure.add_argument("--json", action="store_true")
    configure.add_argument("--yes", action="store_true")

    migrate = commands.add_parser(
        "migrate-authenticated-origin",
        help="Migrate an existing managed scope to connector-exclusive Unix-socket origins",
    )
    migrate.add_argument("name")
    migrate.add_argument("--scope", required=True)
    migrate.add_argument("--zone", required=True, help="Existing bound Cloudflare zone")
    migrate.add_argument("--json", action="store_true")

    route = commands.add_parser("route", help="Project-owned public hostname/DNS routes")
    route_commands = route.add_subparsers(dest="route_command", required=True)

    inventory = route_commands.add_parser("inventory", help="Read host-side managed public-route ownership")
    inventory.add_argument("name")
    inventory.add_argument("--scope", required=True)
    inventory.add_argument("--json", action="store_true")

    register = route_commands.add_parser(
        "register",
        help="Register one exact public hostname through the tunnel to an existing trusted-LAN route",
    )
    register.add_argument("name")
    register.add_argument("--scope", required=True)
    register.add_argument("--owner-repo", required=True)
    register.add_argument("--environment", required=True)
    register.add_argument("--app-slug", required=True)
    register.add_argument("--public-hostname", required=True)
    register.add_argument("--origin-hostname", required=True, help="Existing Project Forge .local Caddy hostname")
    register.add_argument("--json", action="store_true")
    register.add_argument("--yes", action="store_true")

    remove = route_commands.add_parser("remove", help="Remove one exact owned Cloudflare public route")
    remove.add_argument("name")
    remove.add_argument("--scope", required=True)
    remove.add_argument("--owner-repo", required=True)
    remove.add_argument("--environment", required=True)
    remove.add_argument("--app-slug", required=True)
    remove.add_argument("--json", action="store_true")
    remove.add_argument("--yes", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.provider != "cloudflare":
            raise DeploymentKitError(f"Unsupported public-ingress provider: {args.provider}")
        if args.command == "status":
            _print(cloudflare_ingress_status(args.name, args.scope), as_json=args.json)
            return 0
        if args.command == "doctor":
            _print(cloudflare_ingress_doctor(args.name, args.scope), as_json=args.json)
            return 0
        if args.command == "configure":
            token = _token()
            plan = plan_cloudflare_ingress(
                args.name,
                scope=args.scope,
                zone_name=args.zone,
                api_token=token,
                tunnel_name=args.tunnel_name,
                authenticated_origin=args.authenticated_origin,
            )
            _print(plan, as_json=False)
            _confirm(
                args,
                HOST_PUBLIC_INGRESS_WRITE_PHRASE,
                f"configure Cloudflare public ingress scope {args.scope} on target {args.name}",
            )
            _print(apply_cloudflare_ingress(plan, api_token=token), as_json=args.json)
            return 0
        if args.command == "migrate-authenticated-origin":
            token = _token()
            preplan_freeze_acknowledgement = (
                f"{AUTHENTICATED_ORIGIN_CHANGE_FREEZE_PHRASE} ACTIVE scope={args.scope}"
            )
            _confirm(
                args,
                preplan_freeze_acknowledgement,
                "confirm that all external Cloudflare tunnel-configuration writers are frozen for this scope before planning",
            )
            plan = plan_authenticated_origin_migration(
                args.name,
                scope=args.scope,
                zone_name=args.zone,
                api_token=token,
                change_freeze_active_acknowledgement=preplan_freeze_acknowledgement,
            )
            _print(plan, as_json=False)
            _confirm(
                args,
                AUTHENTICATED_ORIGIN_MIGRATION_PHRASE,
                f"migrate existing Cloudflare ingress scope {args.scope} on target {args.name}",
            )
            _confirm(
                args,
                plan["requiredChangeFreezeAcknowledgement"],
                "acknowledge the operator-controlled Cloudflare change freeze for this migration plan",
            )
            _print(
                apply_authenticated_origin_migration(
                    plan,
                    api_token=token,
                    change_freeze_acknowledgement=plan["requiredChangeFreezeAcknowledgement"],
                ),
                as_json=args.json,
            )
            return 0
        if args.command == "route" and args.route_command == "inventory":
            _print(cloudflare_route_inventory(args.name, args.scope), as_json=args.json)
            return 0
        if args.command == "route" and args.route_command == "register":
            token = _token()
            plan = plan_public_route(
                args.name,
                scope=args.scope,
                owner_repo=args.owner_repo,
                environment=args.environment,
                app_slug=args.app_slug,
                public_hostname=args.public_hostname,
                origin_hostname=args.origin_hostname,
                api_token=token,
            )
            _print(plan, as_json=False)
            if plan["action"] == "already-configured":
                _print({"state": "already-configured", "route": plan["route"], "mutated": False}, as_json=args.json)
                return 0
            _confirm(
                args,
                PUBLIC_INGRESS_ROUTE_WRITE_PHRASE,
                f"publish {args.public_hostname} for {args.owner_repo}/{args.environment}/{args.app_slug}",
            )
            _print(apply_public_route(plan, api_token=token), as_json=args.json)
            return 0
        if args.command == "route" and args.route_command == "remove":
            token = _token()
            plan = plan_public_route_removal(
                args.name,
                scope=args.scope,
                owner_repo=args.owner_repo,
                environment=args.environment,
                app_slug=args.app_slug,
                api_token=token,
            )
            _print(plan, as_json=False)
            _confirm(
                args,
                PUBLIC_INGRESS_ROUTE_REMOVE_PHRASE,
                f"remove public route {plan['route']['publicHostname']}",
            )
            _print(apply_public_route_removal(plan, api_token=token), as_json=args.json)
            return 0
        raise DeploymentKitError("Unsupported Cloudflare ingress command.")
    except DeploymentKitError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
