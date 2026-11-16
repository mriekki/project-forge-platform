"""CLI for scoped destructive Project tear-down."""

from __future__ import annotations

import argparse
import json
import sys

from .errors import DeploymentKitError
from .teardown import (
    PRODUCTION_DATA_DELETE_PHRASE,
    PUBLIC_INGRESS_ROUTE_REMOVE_PHRASE,
    TEAR_DOWN_WRITE_PHRASE,
    normalize_teardown_spec,
    parse_environment_scopes,
    parse_environment_targets,
    render_teardown_summary,
    target_inventory,
    tear_down_project,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="project-forge-deploy tear-down",
        description=(
            "Remove one named Kit-managed environment, all explicitly bound environments, "
            "and/or exact-package local Docker state. Remote tear-down deletes persistent "
            "application data for selected environments while preserving shared Project Forge platform state."
        ),
    )
    parser.add_argument(
        "scope",
        help="local, all, or one exact named environment such as demo, staging, qa, or production",
    )
    parser.add_argument("--owner-repo", required=True)
    parser.add_argument("--app-slug", required=True)
    parser.add_argument(
        "--environment-target",
        action="append",
        default=[],
        metavar="ENV=TARGET",
        help="Explicit named environment-to-target binding; repeat as needed.",
    )
    parser.add_argument(
        "--public-ingress-scope",
        action="append",
        default=[],
        metavar="ENV=SCOPE",
        help=(
            "Optional exact environment-to-public-ingress-scope binding discovered from target inventory; "
            "repeat as needed. Selected public routes are removed before LAN/runtime cleanup."
        ),
    )
    parser.add_argument(
        "--production-environment",
        action="append",
        default=[],
        metavar="ENV",
        help=(
            "Classify an additional named environment as Production for the stronger data-deletion gate. "
            "The literal 'production' environment is always Production."
        ),
    )
    parser.add_argument(
        "--local-package",
        help=(
            "Exact local Docker package identity, e.g. ghcr.io/owner/package. "
            "Required for local; optional for all."
        ),
    )
    parser.add_argument(
        "--authorization",
        help=f"Required destructive phrase: {TEAR_DOWN_WRITE_PHRASE}",
    )
    parser.add_argument(
        "--production-data-authorization",
        help=(
            "Additional phrase required whenever selected environments include Production data: "
            f"{PRODUCTION_DATA_DELETE_PHRASE}"
        ),
    )
    parser.add_argument(
        "--public-ingress-authorization",
        help=(
            "Additional phrase required whenever selected environments include public ingress cleanup: "
            f"{PUBLIC_INGRESS_ROUTE_REMOVE_PHRASE}"
        ),
    )
    return parser.parse_args(argv)


def _preview(spec: dict[str, object]) -> dict[str, object]:
    production = bool(spec["productionEnvironments"])
    public_ingress = bool(spec["publicIngressScopes"])
    return {
        "schemaVersion": 3,
        "ownerRepo": spec["ownerRepo"],
        "appSlug": spec["appSlug"],
        "scope": spec["scope"],
        "environmentTargets": spec["environmentTargets"],
        "publicIngressScopes": spec["publicIngressScopes"],
        "localPackage": spec["localPackage"],
        "productionEnvironments": spec["productionEnvironments"],
        "destructive": True,
        "deletesPersistentData": bool(spec["environmentTargets"]),
        "deletesProductionData": production,
        "removesPublicIngress": public_ingress,
        "removesUnreferencedRemoteImages": bool(spec["environmentTargets"]),
        "preservesSharedPlatform": True,
        "preservesSharedPublicIngressRuntime": True,
        "preservesUnrelatedProjects": True,
        "deletesGhcrPackage": False,
        "requiredAuthorization": TEAR_DOWN_WRITE_PHRASE,
        "requiredProductionDataAuthorization": PRODUCTION_DATA_DELETE_PHRASE if production else None,
        "requiredPublicIngressAuthorization": (
            PUBLIC_INGRESS_ROUTE_REMOVE_PHRASE if public_ingress else None
        ),
    }


def inventory_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="project-forge-deploy target inventory",
        description=(
            "Read shared platform state plus application-owned resources that are valid tear-down candidates "
            "on one target. This command is read-only and does not require a consumer repository."
        ),
    )
    parser.add_argument("name", help="Logical Project Forge target profile")
    parser.add_argument(
        "--ingress-scope",
        action="append",
        default=[],
        metavar="SCOPE",
        help=(
            "Additional public-ingress scope to inspect when it cannot be inferred from managed application "
            "or LAN-route environment names; repeat as needed."
        ),
    )
    parser.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(argv)
        result = target_inventory(args.name, ingress_scopes=args.ingress_scope)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("TARGET INVENTORY")
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except DeploymentKitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        bindings = parse_environment_targets(args.environment_target)
        public_bindings = parse_environment_scopes(args.public_ingress_scope)
        spec = normalize_teardown_spec(
            owner_repo=args.owner_repo,
            app_slug=args.app_slug,
            scope=args.scope,
            environment_targets=bindings,
            local_package=args.local_package,
            production_environments=args.production_environment,
            public_ingress_scopes=public_bindings,
        )
        preview = _preview(spec)

        missing_general = args.authorization != TEAR_DOWN_WRITE_PHRASE
        needs_production = bool(spec["productionEnvironments"])
        missing_production = (
            needs_production
            and args.production_data_authorization != PRODUCTION_DATA_DELETE_PHRASE
        )
        needs_public_ingress = bool(spec["publicIngressScopes"])
        missing_public_ingress = (
            needs_public_ingress
            and args.public_ingress_authorization != PUBLIC_INGRESS_ROUTE_REMOVE_PHRASE
        )
        if missing_general or missing_production or missing_public_ingress:
            print("PROJECT TEAR-DOWN PREVIEW")
            print(render_teardown_summary(preview))
            if missing_general:
                print(
                    f"ERROR: destructive tear-down requires --authorization {TEAR_DOWN_WRITE_PHRASE!r}",
                    file=sys.stderr,
                )
            if missing_production:
                print(
                    "ERROR: Production persistent-data deletion requires "
                    f"--production-data-authorization {PRODUCTION_DATA_DELETE_PHRASE!r}",
                    file=sys.stderr,
                )
            if missing_public_ingress:
                print(
                    "ERROR: public-ingress removal requires "
                    f"--public-ingress-authorization {PUBLIC_INGRESS_ROUTE_REMOVE_PHRASE!r}",
                    file=sys.stderr,
                )
            return 2

        result = tear_down_project(spec)
        print("PROJECT TEAR-DOWN COMPLETE")
        print(render_teardown_summary(result))
        return 0
    except DeploymentKitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
