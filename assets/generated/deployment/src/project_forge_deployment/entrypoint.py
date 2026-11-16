"""Top-level console entrypoint for Deployment Kit command groups.

Command groups are loaded lazily so an optional capability defect cannot prevent
unrelated Deployment Kit commands from starting.
"""

from __future__ import annotations

import sys


def access_main(argv: list[str]) -> int:
    from .access_cli import main

    return main(argv)


def app_main(argv: list[str]) -> int:
    from .app_cli import main

    return main(argv)


def core_main(argv: list[str]) -> int:
    from .cli import main

    return main(argv)


def environment_main(argv: list[str]) -> int:
    from .environment_cli import main

    return main(argv)


def ingress_main(argv: list[str]) -> int:
    from .ingress_cli import main

    return main(argv)


def local_main(argv: list[str]) -> int:
    from .local_cli import main

    return main(argv)


def registry_main(argv: list[str]) -> int:
    from .registry_cli import main

    return main(argv)


def sqlite_main(argv: list[str]) -> int:
    from .sqlite_cli import main

    return main(argv)


def target_inventory_main(argv: list[str]) -> int:
    from .teardown_cli import inventory_main

    return inventory_main(argv)


def teardown_main(argv: list[str]) -> int:
    from .teardown_cli import main

    return main(argv)


def topology_main(argv: list[str]) -> int:
    from .topology_cli import main

    return main(argv)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) >= 2 and args[0] == "target" and args[1] == "inventory":
        return target_inventory_main(args[2:])
    if args and args[0] == "access":
        return access_main(args[1:])
    if args and args[0] == "app":
        return app_main(args[1:])
    if args and args[0] == "environment":
        return environment_main(args[1:])
    if args and args[0] == "ingress":
        return ingress_main(args[1:])
    if args and args[0] == "local":
        return local_main(args[1:])
    if args and args[0] == "registry":
        return registry_main(args[1:])
    if args and args[0] == "sqlite":
        return sqlite_main(args[1:])
    if args and args[0] == "tear-down":
        return teardown_main(args[1:])
    if args and args[0] == "topology":
        return topology_main(args[1:])
    if args[:2] in (["target", "--help"], ["target", "-h"]):
        print("Additional command: inventory  Read app-owned tear-down candidates without writes")
    if not args or args == ["--help"] or args == ["-h"]:
        print("Command group: access  Read-only strict SSH target-access diagnosis")
        print("Command group: app  Remote immutable application runtime inventory/deployment")
        print("Command group: environment  Portable profiles, Home Lab onboarding, and image transfer")
        print("Command group: ingress  Optional public ingress such as Cloudflare Tunnel")
        print("Command group: local  Loopback-only workstation application runtime")
        print("Command group: registry  Read-only exact-image registry access verification")
        print("Command group: sqlite  SQLite persistence import/backup/migration/rollback checks")
        print("Command group: tear-down  Scoped destructive Project environment/local cleanup")
        print("Command group: topology  Project-owned logical environment binding")
        print("Target command: inventory  Read app-owned tear-down candidates without writes")
    return core_main(args)
