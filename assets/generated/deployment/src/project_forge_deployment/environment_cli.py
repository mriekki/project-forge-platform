"""CLI for portable developer environment definitions and remote setup orchestration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .environment_probe import (
    DEFAULT_PROBE_IMAGE,
    ENVIRONMENT_PROOF_WRITE_PHRASE,
    PRODUCTION_ENVIRONMENT_PROOF_WRITE_PHRASE,
    plan_environment_proof,
    run_environment_proof,
)
from .environment_setup import remote_setup_plan, remote_setup_status
from .errors import DeploymentKitError
from .home_lab import HOME_LAB_BOOTSTRAP_PHRASE, apply_home_lab_bootstrap, plan_home_lab_bootstrap
from .image_transfer import transfer_image, verify_local_image
from .portable_profile import apply_import, export_bundle, load_bundle, plan_import, write_bundle
from .profile_migration import PERSONAL_PROFILE_MIGRATION_PHRASE, migrate_current_workstation
from .profile_repository import (
    PERSONAL_PROFILE_WRITE_PHRASE,
    ensure_profile_repository,
    publish_profile,
    repository_status,
    sync_profile,
)


LOCAL_PROFILE_IMPORT_PHRASE = "[LOCAL PROFILE IMPORT]"
REMOTE_IMAGE_TRANSFER_PHRASE = "[REMOTE IMAGE TRANSFER]"


def _print(value: Any, *, as_json: bool = False) -> None:
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
    if getattr(args, "yes", False):
        return
    entered = input(f"Type {phrase} to {action}: ").strip()
    if entered != phrase:
        raise DeploymentKitError(f"{action.capitalize()} was not authorized.")


def _setup_readiness(result: dict[str, Any], *, require_deployment_path: bool) -> dict[str, Any]:
    required_phases = ["workspace", "targetDefinition", "targetAccess", "hostPlatform"]
    expected_states = {
        "workspace": "ready",
        "targetDefinition": "ready",
        "targetAccess": "ready",
        "hostPlatform": "ready",
    }
    if require_deployment_path:
        required_phases.append("deploymentPath")
        expected_states["deploymentPath"] = "proven"

    not_ready = [
        phase
        for phase in required_phases
        if result["phases"][phase]["state"] != expected_states[phase]
    ]
    return {
        "ready": not not_ready,
        "requiredThrough": "deploymentPath" if require_deployment_path else "hostPlatform",
        "requiredPhases": required_phases,
        "notReadyPhases": not_ready,
        "applicationRequired": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-forge-deploy environment")
    groups = parser.add_subparsers(dest="group", required=True)

    setup = groups.add_parser(
        "setup",
        help="Read-only remote setup status/plan orchestration across target access, host platform, and proof readiness",
    )
    setup_sub = setup.add_subparsers(dest="command", required=True)
    setup_status = setup_sub.add_parser("status", help="Show one terminal readiness model for a remote target")
    setup_status.add_argument("name")
    setup_status.add_argument("--json", action="store_true")
    setup_check = setup_sub.add_parser(
        "check",
        help="Return success only when the requested remote setup readiness contract is satisfied",
    )
    setup_check.add_argument("name")
    setup_check.add_argument("--owner-repo")
    setup_check.add_argument("--environment")
    setup_check.add_argument(
        "--production",
        action="store_true",
        help="Require proof evidence classified as Production; requires owner/environment proof context",
    )
    setup_check.add_argument("--json", action="store_true")
    setup_plan = setup_sub.add_parser("plan", help="Show the exact next deterministic remote setup action")
    setup_plan.add_argument("name")
    setup_plan.add_argument("--owner-repo")
    setup_plan.add_argument("--environment")
    setup_plan.add_argument(
        "--production",
        action="store_true",
        help="Classify the optional proof environment as Production",
    )
    setup_plan.add_argument("--json", action="store_true")

    profile = groups.add_parser("profile", help="Personal/portable non-secret target profile operations")
    profile_sub = profile.add_subparsers(dest="command", required=True)

    status = profile_sub.add_parser("status", help="Inspect the authenticated developer's private project-forge-profile repository")
    status.add_argument("--json", action="store_true")

    ensure = profile_sub.add_parser(
        "ensure",
        help="Create/initialize the authenticated developer's private project-forge-profile repository when missing",
    )
    ensure.add_argument("--json", action="store_true")
    ensure.add_argument("--yes", action="store_true")

    migrate = profile_sub.add_parser(
        "migrate",
        help="One-time adoption of this workstation's existing target definitions into the personal profile model",
    )
    migrate.add_argument("--json", action="store_true")
    migrate.add_argument("--yes", action="store_true")

    sync = profile_sub.add_parser(
        "sync",
        help="Fetch/validate the personal profile, update last-known-good cache, and optionally import missing definitions",
    )
    sync.add_argument("--apply", action="store_true", help="Create only missing non-conflicting local target profiles")
    sync.add_argument("--json", action="store_true")

    publish = profile_sub.add_parser(
        "publish",
        help="Merge new non-conflicting local target definitions into the private personal profile",
    )
    publish.add_argument("--json", action="store_true")
    publish.add_argument("--yes", action="store_true")

    export = profile_sub.add_parser("export", help="Export sanitized target definitions to a portable bundle")
    export.add_argument("--target", action="append", default=[])
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--json", action="store_true")

    preview = profile_sub.add_parser("preview-import", help="Preview a portable bundle without writing local profiles")
    preview.add_argument("bundle", type=Path)
    preview.add_argument("--json", action="store_true")

    apply = profile_sub.add_parser("import", help="Import only non-conflicting portable target definitions")
    apply.add_argument("bundle", type=Path)
    apply.add_argument("--json", action="store_true")
    apply.add_argument("--yes", action="store_true")

    home_lab = groups.add_parser(
        "home-lab",
        help="Password-assisted one-time SSH bootstrap followed by strict per-workstation key access",
    )
    home_lab_sub = home_lab.add_subparsers(dest="command", required=True)
    for command in ("plan", "bootstrap"):
        sub = home_lab_sub.add_parser(command)
        sub.add_argument("name")
        sub.add_argument("--host-name", required=True)
        sub.add_argument("--user", required=True)
        sub.add_argument("--port", type=int, default=22)
        sub.add_argument("--ssh-alias")
        sub.add_argument("--address", help="Optional exact temporary IP; stable host identity remains --host-name/alias")
        sub.add_argument(
            "--protect-key-with-passphrase",
            action="store_true",
            help="Let ssh-keygen prompt locally for a key passphrase; default Home Lab key is unencrypted",
        )
        sub.add_argument("--json", action="store_true")
        if command == "bootstrap":
            sub.add_argument("--yes", action="store_true")

    image = groups.add_parser("image", help="Workstation-mediated exact Docker image transfer")
    image_sub = image.add_subparsers(dest="command", required=True)
    image_check = image_sub.add_parser("check", help="Verify an exact immutable image exists locally")
    image_check.add_argument("--image", required=True)
    image_check.add_argument("--json", action="store_true")
    image_transfer = image_sub.add_parser("transfer", help="Stream an exact local image to a verified target over SSH")
    image_transfer.add_argument("name")
    image_transfer.add_argument("--image", required=True)
    image_transfer.add_argument("--json", action="store_true")
    image_transfer.add_argument("--yes", action="store_true")

    proof = groups.add_parser(
        "proof",
        help="Plan/run a disposable end-to-end deployment proof for one named remote environment",
    )
    proof_sub = proof.add_subparsers(dest="command", required=True)
    for command in ("plan", "run"):
        sub = proof_sub.add_parser(command)
        sub.add_argument("name", help="Logical target profile name")
        sub.add_argument("--owner-repo", required=True)
        sub.add_argument("--environment", required=True)
        sub.add_argument(
            "--production",
            action="store_true",
            help="Classify the named environment as Production even when its name is not literally 'production'",
        )
        sub.add_argument("--probe-image", default=DEFAULT_PROBE_IMAGE)
        sub.add_argument("--json", action="store_true")
        if command == "run":
            sub.add_argument("--yes", action="store_true")

    return parser


def _home_lab_plan(args: argparse.Namespace) -> dict[str, Any]:
    return plan_home_lab_bootstrap(
        args.name,
        host_name=args.host_name,
        user=args.user,
        port=args.port,
        ssh_alias=args.ssh_alias,
        address=args.address,
        protect_key_with_passphrase=args.protect_key_with_passphrase,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.group == "setup" and args.command == "status":
            _print(remote_setup_status(args.name), as_json=args.json)
            return 0
        if args.group == "setup" and args.command == "check":
            if args.production and (args.owner_repo is None or args.environment is None):
                raise DeploymentKitError(
                    "--production requires --owner-repo and --environment for setup readiness checking."
                )
            result = remote_setup_plan(
                args.name,
                owner_repo=args.owner_repo,
                environment=args.environment,
                production=args.production,
            )
            readiness = _setup_readiness(
                result,
                require_deployment_path=args.owner_repo is not None,
            )
            _print({**result, "readinessCheck": readiness}, as_json=args.json)
            return 0 if readiness["ready"] else 2
        if args.group == "setup" and args.command == "plan":
            _print(
                remote_setup_plan(
                    args.name,
                    owner_repo=args.owner_repo,
                    environment=args.environment,
                    production=args.production,
                ),
                as_json=args.json,
            )
            return 0
        if args.group == "profile" and args.command == "status":
            _print(repository_status(), as_json=args.json)
            return 0
        if args.group == "profile" and args.command == "ensure":
            _print(repository_status(), as_json=False)
            _confirm(args, PERSONAL_PROFILE_WRITE_PHRASE, "create/initialize the private personal Project Forge profile when needed")
            _print(ensure_profile_repository(), as_json=args.json)
            return 0
        if args.group == "profile" and args.command == "migrate":
            _confirm(args, PERSONAL_PROFILE_MIGRATION_PHRASE, "migrate this workstation to the personal Project Forge profile model")
            _print(migrate_current_workstation(), as_json=args.json)
            return 0
        if args.group == "profile" and args.command == "sync":
            _print(sync_profile(apply=args.apply), as_json=args.json)
            return 0
        if args.group == "profile" and args.command == "publish":
            _confirm(args, PERSONAL_PROFILE_WRITE_PHRASE, "publish non-secret target definitions to the private personal Project Forge profile")
            _print(publish_profile(), as_json=args.json)
            return 0
        if args.group == "profile" and args.command == "export":
            bundle = export_bundle(args.target or None)
            path = write_bundle(bundle, args.output)
            _print({"path": str(path), "targets": [item["targetName"] for item in bundle["targets"]]}, as_json=args.json)
            return 0
        if args.group == "profile" and args.command == "preview-import":
            _print(plan_import(load_bundle(args.bundle)), as_json=args.json)
            return 0
        if args.group == "profile" and args.command == "import":
            plan = plan_import(load_bundle(args.bundle))
            _print(plan, as_json=False)
            if plan["hasConflicts"]:
                raise DeploymentKitError("Import conflicts must be resolved explicitly; no local profiles were changed.")
            _confirm(args, LOCAL_PROFILE_IMPORT_PHRASE, "import these portable target definitions")
            _print(apply_import(plan), as_json=args.json)
            return 0
        if args.group == "home-lab":
            plan = _home_lab_plan(args)
            _print(plan, as_json=args.json if args.command == "plan" else False)
            if args.command == "plan":
                return 0
            _confirm(args, HOME_LAB_BOOTSTRAP_PHRASE, f"bootstrap Home Lab access for target {args.name}")
            _print(
                apply_home_lab_bootstrap(
                    plan,
                    protect_key_with_passphrase=args.protect_key_with_passphrase,
                ),
                as_json=args.json,
            )
            return 0
        if args.group == "image" and args.command == "check":
            _print(verify_local_image(args.image), as_json=args.json)
            return 0
        if args.group == "image" and args.command == "transfer":
            _print(verify_local_image(args.image), as_json=False)
            _confirm(args, REMOTE_IMAGE_TRANSFER_PHRASE, f"transfer this exact image to target {args.name}")
            _print(transfer_image(args.name, args.image), as_json=args.json)
            return 0
        if args.group == "proof":
            plan = plan_environment_proof(
                args.name,
                owner_repo=args.owner_repo,
                environment=args.environment,
                production=args.production,
                probe_image=args.probe_image,
            )
            if args.command == "plan":
                _print(plan, as_json=args.json)
                return 0 if plan.get("runnable", True) else 2
            if not plan.get("runnable", True):
                _print(plan, as_json=args.json)
                return 2
            if not args.json:
                _print(plan, as_json=False)
            _confirm(
                args,
                plan["requiredAuthorization"],
                f"run a disposable deployment proof for {plan['environment']} on target {plan['targetName']}",
            )
            result = run_environment_proof(plan)
            _print(result, as_json=args.json)
            return 0 if result.get("proof") == "passed" else 2
        raise DeploymentKitError("Unsupported environment command.")
    except DeploymentKitError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


__all__ = [
    "ENVIRONMENT_PROOF_WRITE_PHRASE",
    "PRODUCTION_ENVIRONMENT_PROOF_WRITE_PHRASE",
    "build_parser",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
