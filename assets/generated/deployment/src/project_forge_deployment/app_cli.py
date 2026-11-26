"""CLI for generic immutable application runtime deployment."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import timedelta
from typing import Any

from .app_deployment import (
    app_isolation_check,
    apply_app_deploy,
    apply_app_deploy_from_workstation,
    plan_app_deploy,
    plan_app_rollout,
)
from .app_runtime import (
    APP_DEPLOY_WRITE_PHRASE,
    PRODUCTION_APP_DEPLOY_WRITE_PHRASE,
    app_inventory,
    deploy_write_phrase,
    normalize_app_spec,
)
from .errors import DeploymentKitError
from .sqlite_adapter import assert_app_spec_matches_persistence


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


def _parse_env(items: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for item in items:
        if "=" not in item:
            raise DeploymentKitError("--env entries must use NAME=value form.")
        key, value = item.split("=", 1)
        result.append((key, value))
    return result


def _parse_materials(items: list[str]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for item in items:
        if "=" not in item:
            raise DeploymentKitError("--read-only-material requires NAME=/absolute/container/directory.")
        name, target = item.split("=", 1)
        values.append((name, target))
    return values


def _confirm(args: argparse.Namespace, phrase: str, action: str) -> None:
    if args.yes:
        return
    entered = input(f"Type {phrase} to {action}: ").strip()
    if entered != phrase:
        raise DeploymentKitError(f"{action.capitalize()} was not authorized.")


def _add_isolation_footprint(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name")
    parser.add_argument("--owner-repo", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument(
        "--production",
        action="store_true",
        help="Classify this named environment as Production even when its name is not literally 'production'",
    )
    parser.add_argument("--app-slug", required=True)
    parser.add_argument("--container-name", required=True)
    parser.add_argument("--runtime-port", type=int, required=True)
    parser.add_argument(
        "--persistence-mode",
        choices=("none", "directory"),
        required=True,
    )
    parser.add_argument(
        "--database-file",
        help="Optional intended SQLite database file used only for read-only collision/isolation checks",
    )
    parser.add_argument(
        "--route-hostname",
        action="append",
        default=[],
        help="Optional intended route hostname used only for read-only collision/isolation checks; repeat as needed",
    )


def _add_runtime_contract(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--image", required=True)
    parser.add_argument("--health-path", required=True)
    parser.add_argument("--run-as", required=True)
    parser.add_argument("--data-container-path")
    parser.add_argument("--authentication-epoch-store", action="store_true", help="Opt in to external single-host authentication epoch SQLite storage")
    parser.add_argument(
        "--read-only-material",
        action="append",
        default=[],
        metavar="NAME=/container/directory",
        help="Opt-in root-owned remote material directory; source derived from Project/environment/name",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Non-secret runtime environment value in NAME=value form; repeat as needed",
    )
    parser.add_argument(
        "--image-source",
        choices=("remote-registry", "workstation"),
        default="remote-registry",
        help=(
            "remote-registry preserves the existing target-side pull path; workstation streams an exact local image "
            "over verified SSH so the target does not need registry credentials"
        ),
    )
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-forge-deploy app")
    sub = parser.add_subparsers(dest="command", required=True)

    inventory = sub.add_parser(
        "inventory",
        help="Read Kit-managed application runtime ownership/readiness without writes",
    )
    inventory.add_argument("name")
    inventory.add_argument("--json", action="store_true")
    # Opt in to the same scoped deployment handoff used by administrators.
    # Ordinary inventory retains its original behavior and result schema.
    inventory.add_argument("--publication-run", type=int, help="Exact existing publisher run for a scoped evidence handoff")
    inventory.add_argument("--owner-repo")
    inventory.add_argument("--app-slug")
    inventory.add_argument("--environment")
    inventory.add_argument("--collect-registry", action="store_true", help="Also verify the exact private manifest from this workstation")
    inventory.add_argument("--endpoint", help="Explicitly reported HTTP(S) origin only")
    inventory.add_argument("--human-report", action="append", default=[])
    inventory.add_argument("--pr", type=int)
    inventory.add_argument("--pr-head")
    inventory.add_argument("--pr-base")
    inventory.add_argument("--runtime-max-age-seconds", type=int)
    inventory.add_argument("--human-max-age-seconds", type=int)
    inventory.add_argument("--partial", action="store_true", help="Retain independent evidence when an optional stage fails")
    inventory.add_argument("--output", help="New local evidence export file; never overwrite")

    isolation = sub.add_parser(
        "isolation",
        help="Read current managed ownership/runtime/route/persistence isolation for an application footprint",
    )
    _add_isolation_footprint(isolation)
    isolation.add_argument(
        "--require-clear",
        action="store_true",
        help="Exit nonzero when the read-only isolation result is blocked",
    )
    isolation.add_argument("--json", action="store_true")

    rollout = sub.add_parser(
        "rollout",
        help="Preview application runtime and owned route as one read-only staged rollout",
    )
    _add_isolation_footprint(rollout)
    _add_runtime_contract(rollout)

    deploy = sub.add_parser(
        "deploy",
        help="Deploy one immutable application runtime without modifying routes",
    )
    _add_isolation_footprint(deploy)
    _add_runtime_contract(deploy)
    deploy.add_argument("--yes", action="store_true")
    return parser


def _inventory_evidence(args):
    """Extend the existing explicit inventory path, never a new write gate."""
    scope = (args.owner_repo, args.app_slug, args.environment)
    if args.publication_run is None:
        if any(value is not None for value in (
            *scope, args.endpoint, args.pr, args.pr_head, args.pr_base,
            args.runtime_max_age_seconds, args.human_max_age_seconds, args.output,
        )) or args.collect_registry or args.human_report or args.partial:
            raise ValueError("scoped evidence options require an explicit publisher run")
        return None
    if not args.json or not all(scope):
        raise ValueError("scoped evidence requires exact owner/repo, app, environment and JSON")
    from . import deployment_evidence_handoff as handoff

    if len(args.human_report) > handoff.MAX_REPORTS:
        raise ValueError("too many human reports")
    pr = (args.pr, args.pr_head, args.pr_base)
    if all(value is None for value in pr):
        pr = None
    result = handoff.build_handoff(
        args.owner_repo, app=args.app_slug, environment=args.environment,
        target=args.name, publication_run=args.publication_run,
        endpoint=args.endpoint, collect=True, collect_registry=args.collect_registry,
        documents=[handoff.bounded_read(path) for path in args.human_report],
        pr=pr, partial=args.partial,
        runtime_max_age=timedelta(seconds=300 if args.runtime_max_age_seconds is None else args.runtime_max_age_seconds),
        human_max_age=timedelta(seconds=604800 if args.human_max_age_seconds is None else args.human_max_age_seconds),
        publisher=handoff.publication_status, inventory_collector=handoff.collect_inventory,
        registry_inspector=handoff.observe_registry_manifest, pr_inspector=handoff.pr_fallback,
    )
    handoff.write_export(result, args.output)
    return 2 if result["diagnostics"]["collectionState"] == "incomplete" else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inventory":
            try:
                result_code = _inventory_evidence(args)
            except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError,
                    AttributeError, OverflowError, RecursionError, DeploymentKitError):
                print("Deployment evidence unavailable or inconsistent; inspect exact scoped sources and retry.",
                      file=sys.stderr)
                return 2
            if result_code is not None:
                return result_code
            _print(app_inventory(args.name), as_json=args.json)
            return 0

        production_classified = args.production or args.environment == "production"
        if args.command == "isolation":
            result = app_isolation_check(
                args.name,
                owner_repo=args.owner_repo,
                environment=args.environment,
                production=production_classified,
                app_slug=args.app_slug,
                container_name=args.container_name,
                runtime_port=args.runtime_port,
                persistence_mode=args.persistence_mode,
                database_file=args.database_file,
                route_hostnames=args.route_hostname,
            )
            _print(result, as_json=args.json)
            return 2 if args.require_clear and result["state"] != "clear" else 0

        spec = normalize_app_spec(
            owner_repo=args.owner_repo,
            environment=args.environment,
            app_slug=args.app_slug,
            container_name=args.container_name,
            image=args.image,
            runtime_port=args.runtime_port,
            health_path=args.health_path,
            run_as=args.run_as,
            persistence_mode=args.persistence_mode,
            data_container_path=args.data_container_path,
            environment_variables=_parse_env(args.env),
            read_only_materials=_parse_materials(args.read_only_material),
            authentication_epoch_store=args.authentication_epoch_store,
        )
        assert_app_spec_matches_persistence(args.name, spec)

        if args.command == "rollout":
            rollout_plan = plan_app_rollout(
                args.name,
                spec,
                production=production_classified,
                database_file=args.database_file,
                route_hostnames=args.route_hostname,
            )
            rollout_plan["imageSource"] = args.image_source
            rollout_plan["targetRegistryCredentialRequired"] = args.image_source == "remote-registry"
            _print(rollout_plan, as_json=args.json)
            return 0

        plan = plan_app_deploy(
            args.name,
            spec,
            production=production_classified,
            database_file=args.database_file,
            route_hostnames=args.route_hostname,
        )
        plan_view = {key: value for key, value in plan.items() if key != "spec"}
        plan_view["imageSource"] = args.image_source
        plan_view["productionClassified"] = production_classified
        if args.image_source == "workstation":
            plan_view["targetRegistryCredentialRequired"] = False
        _print(plan_view, as_json=False)
        phrase = PRODUCTION_APP_DEPLOY_WRITE_PHRASE if production_classified else deploy_write_phrase(plan)
        _confirm(
            args,
            phrase,
            f"deploy {plan['appSlug']} ({plan['environment']}) on target {args.name}",
        )
        result = (
            apply_app_deploy_from_workstation(plan)
            if args.image_source == "workstation"
            else apply_app_deploy(plan)
        )
        _print(result, as_json=args.json)
        return 0
    except DeploymentKitError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


__all__ = [
    "APP_DEPLOY_WRITE_PHRASE",
    "PRODUCTION_APP_DEPLOY_WRITE_PHRASE",
    "build_parser",
    "main",
]
