"""CLI for the SQLite persistence adapter."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any
from .errors import DeploymentKitError
from .sqlite_adapter import authorization_phrase, apply_sqlite_operation, normalize_sqlite_request, plan_sqlite_operation, sqlite_inventory
from .sqlite_import_recovery import (
    apply_sqlite_import_recovery,
    authorization_phrase as recovery_authorization_phrase,
    plan_sqlite_import_recovery,
)


def _print(value: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True)); return
    if isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: {json.dumps(item, sort_keys=True) if isinstance(item,(dict,list)) else item}")
    else: print(value)


def _parse_env(items: list[str]) -> list[tuple[str,str]]:
    out=[]
    for item in items:
        if '=' not in item: raise DeploymentKitError("--maintenance-env entries must use NAME=value form.")
        out.append(tuple(item.split('=',1)))
    return out


def _load_recovery_manifest(path: str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DeploymentKitError(f"Could not read recovery manifest as UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise DeploymentKitError("Recovery manifest root must be a JSON object.")
    return value


def _confirm(args: argparse.Namespace, phrase: str, action: str) -> None:
    if args.yes: return
    if input(f"Type {phrase} to {action}: ").strip() != phrase:
        raise DeploymentKitError(f"{action.capitalize()} was not authorized.")


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('name')
    parser.add_argument('--owner-repo', required=True)
    parser.add_argument('--environment', required=True)
    parser.add_argument(
        '--production',
        action='store_true',
        help="Classify this named environment as Production even when its name is not literally 'production'",
    )
    parser.add_argument('--app-slug', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--maintenance-env', action='append', default=[], help='Non-secret image maintenance environment value in NAME=value form; repeat as needed')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--yes', action='store_true')


def _recovery_manifest_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--recovery-manifest', help='Optional strict non-secret JSON declaration of recovery dependencies and authentication policy')


def _import_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--run-as', required=True)
    parser.add_argument('--database-file', required=True)
    parser.add_argument('--source-database', required=True)


def build_parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(prog='project-forge-deploy sqlite')
    sub=parser.add_subparsers(dest='command',required=True)
    inv=sub.add_parser('inventory',help='Read SQLite persistence reservations without writes'); inv.add_argument('name'); inv.add_argument('--json',action='store_true')
    imp=sub.add_parser('import',help='Import an existing SQLite DB via the exact image online-backup contract'); _common(imp); _import_args(imp)
    recover=sub.add_parser('recover-import',help='Recover a verified failed import without overwriting or recopying the database'); _common(recover); _import_args(recover)
    backup=sub.add_parser('backup',help='Create a verified SQLite database backup with the exact image'); _common(backup); _recovery_manifest_arg(backup)
    migrate=sub.add_parser('migrate',help='Create required database backup and run exact-image SQLite migration'); _common(migrate); _recovery_manifest_arg(migrate)
    migrate.add_argument('--first-install',action='store_true'); migrate.add_argument('--run-as'); migrate.add_argument('--database-file')
    check=sub.add_parser('rollback-check',help='Verify that an exact rollback image accepts the current SQLite state'); _common(check)
    return parser


def main(argv: list[str]|None=None) -> int:
    args=build_parser().parse_args(argv)
    try:
        if args.command=='inventory': _print(sqlite_inventory(args.name),as_json=args.json); return 0
        if args.command=='migrate' and getattr(args,'first_install',False) and getattr(args,'recovery_manifest',None):
            raise DeploymentKitError("--recovery-manifest is supported only for existing-database SQLite migration, not --first-install.")
        production_classified = args.production or args.environment == 'production'
        request=normalize_sqlite_request(owner_repo=args.owner_repo,environment=args.environment,app_slug=args.app_slug,image=args.image,
            maintenance_environment=_parse_env(args.maintenance_env),run_as=getattr(args,'run_as',None),database_file=getattr(args,'database_file',None),
            source_database=getattr(args,'source_database',None),first_install=getattr(args,'first_install',False),
            recovery_scope=_load_recovery_manifest(getattr(args,'recovery_manifest',None)))
        if args.command=='recover-import':
            plan=plan_sqlite_import_recovery(args.name,request,production=production_classified)
            _print({k:v for k,v in plan.items() if k!='request'},as_json=False)
            phrase=recovery_authorization_phrase(plan)
            _confirm(args,phrase,f"recover SQLite import for {plan['appSlug']} ({plan['environment']}) on target {args.name}")
            _print(apply_sqlite_import_recovery(plan),as_json=args.json); return 0
        plan=plan_sqlite_operation(args.name,args.command,request,production=production_classified)
        _print({k:v for k,v in plan.items() if k!='spec'},as_json=False)
        phrase=authorization_phrase(plan)
        _confirm(args,phrase,f"run SQLite {args.command} for {plan['appSlug']} ({plan['environment']}) on target {args.name}")
        _print(apply_sqlite_operation(plan),as_json=args.json); return 0
    except DeploymentKitError as error:
        print(f"ERROR: {error}",file=sys.stderr); return 2
