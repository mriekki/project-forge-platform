"""Command-line interface for the Deployment Kit."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .box_platform import (
    HOST_PLATFORM_WRITE_PHRASE,
    apply_platform_change,
    plan_platform_change,
    platform_doctor,
    platform_proxy_peer,
    platform_status,
)
from .doctor import target_doctor, workstation_doctor
from .errors import DeploymentKitError
from .keys import add_key_to_agent, agent_status, create_dedicated_key, public_key_info
from .profiles import load_profile, save_profile, validate_profile
from .route_registry import (
    ROUTE_REMOVE_PHRASE,
    ROUTE_WRITE_PHRASE,
    apply_route_change,
    plan_route_registration,
    plan_route_removal,
    route_inventory,
)
from .ssh import verify_access
from .trust import (
    apply_trust_plan,
    candidate_view,
    plan_console_verified_trust,
    scan_host_keys,
    trust_plan_view,
)


LOCAL_WRITE_PHRASE = "[LOCAL CONFIG WRITE]"
KEY_WRITE_PHRASE = "[LOCAL KEY WRITE]"
AGENT_WRITE_PHRASE = "[SSH AGENT WRITE]"
TRUST_WRITE_PHRASE = "[LOCAL TRUST WRITE]"
TRUST_ROTATE_PHRASE = "[LOCAL TRUST ROTATION]"


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
    elif isinstance(value, list):
        for item in value:
            print(json.dumps(item, sort_keys=True))
    else:
        print(value)


def _confirm(args: argparse.Namespace, phrase: str, action: str) -> None:
    if args.yes:
        return
    entered = input(f"Type {phrase} to {action}: ").strip()
    if entered != phrase:
        raise DeploymentKitError(f"{action.capitalize()} was not authorized.")


def _configure(args: argparse.Namespace) -> int:
    profile = {
        "schemaVersion": 1,
        "targetName": args.name,
        "targetOs": args.target_os,
        "hostName": args.host_name,
        "sshAlias": args.ssh_alias,
        "user": args.user,
        "port": args.port,
        "identityFile": args.identity_file,
        "knownHostsFile": args.known_hosts_file,
        "addressOverride": args.address_override,
    }
    print(json.dumps(profile, indent=2))
    _confirm(args, LOCAL_WRITE_PHRASE, "write this user-scoped target profile")
    path = save_profile(profile)
    print(f"Wrote target profile: {path}")
    return 0


def _set_address(args: argparse.Namespace) -> int:
    profile = load_profile(args.name)
    proposed = dict(profile)
    proposed["addressOverride"] = args.address
    proposed = validate_profile(proposed, expected_target_name=args.name)
    evidence = verify_access(proposed)
    _print(
        {
            "targetName": args.name,
            "currentOverride": profile["addressOverride"],
            "proposedOverride": proposed["addressOverride"],
            "strictVerification": evidence,
        },
        as_json=False,
    )
    _confirm(args, LOCAL_WRITE_PHRASE, "store this separately verified address override")
    save_profile(proposed)
    print(f"Stored address override for {args.name}: {proposed['addressOverride']}")
    return 0


def _clear_address(args: argparse.Namespace) -> int:
    profile = load_profile(args.name)
    if profile["addressOverride"] is None:
        print(f"No address override is set for {args.name}.")
        return 0
    _print(
        {
            "targetName": args.name,
            "currentOverride": profile["addressOverride"],
            "proposedOverride": None,
        },
        as_json=False,
    )
    _confirm(args, LOCAL_WRITE_PHRASE, "clear this target address override")
    profile["addressOverride"] = None
    save_profile(profile)
    print(f"Cleared address override for {args.name}.")
    return 0


def _platform_change(args: argparse.Namespace) -> int:
    plan = plan_platform_change(args.name, args.command)
    _print(plan, as_json=False)
    _confirm(
        args,
        HOST_PLATFORM_WRITE_PHRASE,
        f"{args.command} the shared host platform on target {args.name}",
    )
    _print(apply_platform_change(plan), as_json=args.json)
    return 0


def _route_change(args: argparse.Namespace) -> int:
    if args.command == "register":
        plan = plan_route_registration(
            args.name,
            owner_repo=args.owner_repo,
            environment=args.environment,
            app_slug=args.app_slug,
            upstream_container=args.upstream_container,
            upstream_port=args.upstream_port,
            hostnames=args.hostname,
        )
        phrase = ROUTE_WRITE_PHRASE
        action = f"register/update route {plan['route']['routeId']} on target {args.name}"
    else:
        plan = plan_route_removal(
            args.name,
            owner_repo=args.owner_repo,
            environment=args.environment,
            app_slug=args.app_slug,
        )
        phrase = ROUTE_REMOVE_PHRASE
        action = f"remove route {plan['route']['routeId']} from target {args.name}"
    _print(plan, as_json=False)
    _confirm(args, phrase, action)
    _print(apply_route_change(plan), as_json=args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="project-forge-deploy")
    subparsers = parser.add_subparsers(dest="group", required=True)

    workstation = subparsers.add_parser("workstation", help="Workstation setup/readiness operations")
    workstation_sub = workstation.add_subparsers(dest="command", required=True)
    ws_doctor = workstation_sub.add_parser("doctor", help="Inspect workstation readiness without modifying it")
    ws_doctor.add_argument("--json", action="store_true")

    target = subparsers.add_parser("target", help="Logical deployment target operations")
    target_sub = target.add_subparsers(dest="command", required=True)

    target_doctor_parser = target_sub.add_parser("doctor", help="Inspect one target without modifying it")
    target_doctor_parser.add_argument("name")
    target_doctor_parser.add_argument("--json", action="store_true")

    show = target_sub.add_parser("show", help="Show normalized non-secret target profile")
    show.add_argument("name")
    show.add_argument("--json", action="store_true")

    verify = target_sub.add_parser("verify", help="Verify strict public-key SSH access without remote writes")
    verify.add_argument("name")
    verify.add_argument("--json", action="store_true")

    configure = target_sub.add_parser("configure", help="Write a user-scoped target profile")
    configure.add_argument("name")
    configure.add_argument("--target-os", default="ubuntu")
    configure.add_argument("--host-name", required=True)
    configure.add_argument("--ssh-alias", required=True)
    configure.add_argument("--user", required=True)
    configure.add_argument("--port", type=int, default=22)
    configure.add_argument("--identity-file", required=True)
    configure.add_argument("--known-hosts-file", required=True)
    configure.add_argument("--address-override")
    configure.add_argument("--yes", action="store_true", help="Accept the bounded local profile write")

    key_create = target_sub.add_parser(
        "key-create",
        help="Create the configured dedicated ed25519 key without exposing its passphrase to this tool",
    )
    key_create.add_argument("name")
    key_create.add_argument("--yes", action="store_true")

    key_public = target_sub.add_parser(
        "key-public",
        help="Show the dedicated public key and fingerprint for console-assisted installation",
    )
    key_public.add_argument("name")
    key_public.add_argument("--json", action="store_true")

    agent_check = target_sub.add_parser("agent-status", help="Inspect whether the dedicated key is loaded")
    agent_check.add_argument("name")
    agent_check.add_argument("--json", action="store_true")

    agent_add = target_sub.add_parser(
        "agent-add",
        help="Load the configured dedicated key into an already-running SSH agent",
    )
    agent_add.add_argument("name")
    agent_add.add_argument("--yes", action="store_true")

    agent_session = target_sub.add_parser(
        "agent-session",
        help="Reuse a workstation SSH agent/key and run one normal Deployment Kit command",
    )
    agent_session.add_argument("name", help="Exact configured SSH target identity to load")
    agent_session.add_argument(
        "session_args", nargs=argparse.REMAINDER,
        help="After --, a normal Deployment Kit command (with its usual authorization gates)",
    )

    agent_run = target_sub.add_parser(
        "agent-run",
        help="Run one repository-defined local program with the target's SSH agent, no shell",
    )
    agent_run.add_argument("name", help="Exact configured SSH target identity to load")
    agent_run.add_argument(
        "run_args", nargs=argparse.REMAINDER,
        help="After --, exact executable and arguments for a normal local program",
    )

    trust_candidates = target_sub.add_parser(
        "trust-candidates",
        help="Read candidate host-key fingerprints; candidates are never trusted by discovery",
    )
    trust_candidates.add_argument("name")
    trust_candidates.add_argument(
        "--address",
        help="Exact current IP independently obtained from the trusted target console",
    )
    trust_candidates.add_argument("--json", action="store_true")

    trust_enroll = target_sub.add_parser(
        "trust-enroll",
        help="Enroll one host key only when it matches the independently observed console fingerprint",
    )
    trust_enroll.add_argument("name")
    trust_enroll.add_argument("--fingerprint", required=True)
    trust_enroll.add_argument("--address")
    trust_enroll.add_argument("--yes", action="store_true")

    trust_rotate = target_sub.add_parser(
        "trust-rotate",
        help="Explicitly replace existing target trust after independent console verification",
    )
    trust_rotate.add_argument("name")
    trust_rotate.add_argument("--fingerprint", required=True)
    trust_rotate.add_argument("--address")
    trust_rotate.add_argument("--yes", action="store_true")

    address_set = target_sub.add_parser(
        "address-set",
        help="Store an IP override only after strict SSH verification against existing target identity",
    )
    address_set.add_argument("name")
    address_set.add_argument("--address", required=True)
    address_set.add_argument("--yes", action="store_true")

    address_clear = target_sub.add_parser("address-clear", help="Clear a target's temporary address override")
    address_clear.add_argument("name")
    address_clear.add_argument("--yes", action="store_true")

    route = subparsers.add_parser(
        "route",
        help="Owned application route operations on a ready shared host platform",
    )
    route_sub = route.add_subparsers(dest="command", required=True)
    route_inventory_parser = route_sub.add_parser(
        "inventory", help="Read managed route ownership plus legacy route filenames without writes"
    )
    route_inventory_parser.add_argument("name")
    route_inventory_parser.add_argument("--json", action="store_true")

    route_register = route_sub.add_parser(
        "register", help="Create or update one Project/environment-owned Caddy + mDNS route"
    )
    route_register.add_argument("name")
    route_register.add_argument("--owner-repo", required=True)
    route_register.add_argument("--environment", required=True)
    route_register.add_argument("--app-slug", required=True)
    route_register.add_argument("--upstream-container", required=True)
    route_register.add_argument("--upstream-port", type=int, required=True)
    route_register.add_argument("--hostname", action="append", required=True)
    route_register.add_argument("--json", action="store_true")
    route_register.add_argument("--yes", action="store_true")

    route_remove = route_sub.add_parser(
        "remove", help="Remove only one owned route/alias registration, preserving app runtime and data"
    )
    route_remove.add_argument("name")
    route_remove.add_argument("--owner-repo", required=True)
    route_remove.add_argument("--environment", required=True)
    route_remove.add_argument("--app-slug", required=True)
    route_remove.add_argument("--json", action="store_true")
    route_remove.add_argument("--yes", action="store_true")

    platform = subparsers.add_parser(
        "platform",
        help="Shared Ubuntu box platform operations; never registers or removes application routes",
    )
    platform_sub = platform.add_subparsers(dest="command", required=True)
    platform_status_parser = platform_sub.add_parser(
        "status", help="Read shared host-platform state without remote writes"
    )
    platform_status_parser.add_argument("name")
    platform_status_parser.add_argument("--json", action="store_true")
    platform_doctor_parser = platform_sub.add_parser(
        "doctor", help="Read shared host-platform readiness and next action"
    )
    platform_doctor_parser.add_argument("name")
    platform_doctor_parser.add_argument("--json", action="store_true")
    proxy_peer = platform_sub.add_parser(
        "peer-inspect",
        help="Read exact managed Caddy peer identity and review required application convergence",
    )
    proxy_peer.add_argument("name")
    proxy_peer.add_argument("--configured-peer", help="Exact peer IP currently trusted by this application")
    proxy_peer.add_argument("--previous-container-id", help="Previously reviewed Caddy container ID")
    proxy_peer.add_argument("--previous-network-id", help="Previously reviewed Docker network ID")
    proxy_peer.add_argument("--json", action="store_true")
    for command in ("install", "upgrade"):
        change = platform_sub.add_parser(
            command,
            help=(
                "Install shared host platform on a fresh target"
                if command == "install"
                else "Upgrade an already Kit-owned shared host platform"
            ),
        )
        change.add_argument("name")
        change.add_argument("--json", action="store_true")
        change.add_argument("--yes", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.group == "workstation" and args.command == "doctor":
            _print(workstation_doctor(), as_json=args.json)
            return 0
        if args.group == "target" and args.command == "doctor":
            _print(target_doctor(args.name), as_json=args.json)
            return 0
        if args.group == "target" and args.command == "show":
            _print(load_profile(args.name), as_json=args.json)
            return 0
        if args.group == "target" and args.command == "verify":
            _print(verify_access(load_profile(args.name)), as_json=args.json)
            return 0
        if args.group == "target" and args.command == "configure":
            return _configure(args)
        if args.group == "target" and args.command == "key-create":
            profile = load_profile(args.name)
            _print(
                {
                    "targetName": args.name,
                    "identityFile": profile["identityFile"],
                    "keyType": "ed25519",
                    "passphraseHandling": "entered directly into ssh-keygen",
                },
                as_json=False,
            )
            _confirm(args, KEY_WRITE_PHRASE, "create this dedicated workstation key")
            _print(create_dedicated_key(profile), as_json=False)
            return 0
        if args.group == "target" and args.command == "key-public":
            _print(public_key_info(load_profile(args.name)), as_json=args.json)
            return 0
        if args.group == "target" and args.command == "agent-status":
            _print(agent_status(load_profile(args.name)), as_json=args.json)
            return 0
        if args.group == "target" and args.command == "agent-run":
            import subprocess

            command = list(args.run_args)
            if command and command[0] == "--":
                command.pop(0)
            if not command:
                raise DeploymentKitError(
                    "Supply an exact local executable and argv after '--'. "
                    "The agent-run command does not authorize the program's writes."
                )
            from .agent_session import target_agent_session

            with target_agent_session(load_profile(args.name)) as session:
                print(
                    f"SSH agent ready for {session['targetName']} ({session['agent']}); "
                    "the launched program retains its own authorization gates.",
                    file=sys.stderr,
                )
                # No shell, eval, redirection, or implicit --yes. The caller
                # selects an already-reviewed repository-owned program.
                return subprocess.run(command, check=False).returncode
        if args.group == "target" and args.command == "agent-session":
            command = list(args.session_args)
            if command and command[0] == "--":
                command.pop(0)
            if not command or command[:2] == ["target", "agent-session"]:
                raise DeploymentKitError(
                    "Supply a non-nested Deployment Kit subcommand after '--'. "
                    "The SSH-agent session does not authorize remote operations."
                )
            from .agent_session import target_agent_session
            from .entrypoint import main as dispatch

            with target_agent_session(load_profile(args.name)) as session:
                print(
                    f"SSH agent ready for {session['targetName']} ({session['agent']}); "
                    "normal CLI checks and write gates still apply.",
                    file=sys.stderr,
                )
                return dispatch(command)
        if args.group == "target" and args.command == "agent-add":
            profile = load_profile(args.name)
            status = agent_status(profile)
            _print(status, as_json=False)
            if status["loaded"]:
                return 0
            if status["state"] == "agent-unavailable":
                raise DeploymentKitError(
                    "The SSH agent is unavailable. Start/enable it as a separate workstation action; "
                    "this command will not change agent service configuration."
                )
            _confirm(args, AGENT_WRITE_PHRASE, "load this dedicated key into the running SSH agent")
            _print(add_key_to_agent(profile), as_json=False)
            return 0
        if args.group == "target" and args.command == "trust-candidates":
            candidates = scan_host_keys(load_profile(args.name), console_address=args.address)
            _print([candidate_view(item) for item in candidates], as_json=args.json)
            return 0
        if args.group == "target" and args.command in {"trust-enroll", "trust-rotate"}:
            profile = load_profile(args.name)
            rotate = args.command == "trust-rotate"
            plan = plan_console_verified_trust(
                profile,
                fingerprint=args.fingerprint,
                rotate=rotate,
                console_address=args.address,
            )
            _print(trust_plan_view(plan), as_json=False)
            phrase = TRUST_ROTATE_PHRASE if rotate else TRUST_WRITE_PHRASE
            action = (
                "replace existing target trust with this console-verified host key"
                if rotate
                else "enroll this console-verified target host key"
            )
            _confirm(args, phrase, action)
            _print(apply_trust_plan(profile, plan), as_json=False)
            return 0
        if args.group == "target" and args.command == "address-set":
            return _set_address(args)
        if args.group == "target" and args.command == "address-clear":
            return _clear_address(args)
        if args.group == "route" and args.command == "inventory":
            _print(route_inventory(args.name), as_json=args.json)
            return 0
        if args.group == "route" and args.command in {"register", "remove"}:
            return _route_change(args)
        if args.group == "platform" and args.command == "status":
            _print(platform_status(args.name), as_json=args.json)
            return 0
        if args.group == "platform" and args.command == "doctor":
            _print(platform_doctor(args.name), as_json=args.json)
            return 0
        if args.group == "platform" and args.command == "peer-inspect":
            _print(
                platform_proxy_peer(
                    args.name,
                    configured_peer=args.configured_peer,
                    previous_container_id=args.previous_container_id,
                    previous_network_id=args.previous_network_id,
                ),
                as_json=args.json,
            )
            return 0
        if args.group == "platform" and args.command in {"install", "upgrade"}:
            return _platform_change(args)
        raise DeploymentKitError("Unsupported command.")
    except DeploymentKitError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
