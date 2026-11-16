#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "extension"
MANIFEST = SOURCE / "package.json"


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def extension_identity() -> tuple[str, str]:
    manifest = load_manifest()
    publisher = str(manifest["publisher"]).strip()
    name = str(manifest["name"]).strip()
    version = str(manifest["version"]).strip()
    if not publisher or not name or not version:
        raise RuntimeError("Project Forge VS Code extension manifest is incomplete")
    return f"{publisher}.{name}", version


def is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8")
    except OSError:
        return False
    return "microsoft" in release.lower()


def resolve_extensions_root(explicit: Path | None = None) -> tuple[Path, str]:
    if explicit is not None:
        return explicit.expanduser(), "command-line"

    override = os.environ.get("VSCODE_EXTENSIONS")
    if override:
        return Path(override).expanduser(), "VSCODE_EXTENSIONS"

    if not is_wsl():
        return Path.home() / ".vscode" / "extensions", "native-default"

    agent_folder = os.environ.get("VSCODE_AGENT_FOLDER")
    if agent_folder:
        return Path(agent_folder).expanduser() / "extensions", "VSCODE_AGENT_FOLDER"

    home = Path.home()
    candidates = [
        (home / ".vscode-server" / "extensions", "wsl-stable"),
        (home / ".vscode-server-insiders" / "extensions", "wsl-insiders"),
    ]
    existing = [(path, source) for path, source in candidates if path.parent.is_dir()]
    if len(existing) == 1:
        return existing[0]
    if len(existing) > 1:
        roots = ", ".join(str(path) for path, _ in existing)
        raise RuntimeError(
            "Multiple VS Code Server roots are present in WSL "
            f"({roots}). Set --extensions-dir or VSCODE_EXTENSIONS to select the active host explicitly."
        )

    return candidates[0][0], "wsl-stable-default"


def default_extensions_root() -> Path:
    return resolve_extensions_root()[0]


def extension_target(root: Path) -> Path:
    extension_id, version = extension_identity()
    return root / f"{extension_id}-{version}"


def status(root: Path) -> dict[str, Any]:
    extension_id, version = extension_identity()
    target = extension_target(root)
    files_present = target.is_dir() and all(
        (target / name).is_file() for name in ("package.json", "extension.js", "README.md")
    )
    return {
        "extensionId": extension_id,
        "version": version,
        "status": "files-present" if files_present else "not-installed",
        "path": str(target),
        "reloadRequired": False,
        "activationStatus": "unverified" if files_present else "not-applicable",
        "activationVerified": False,
        "verificationRequired": files_present,
    }


def install(root: Path) -> dict[str, Any]:
    extension_id, version = extension_identity()
    root.mkdir(parents=True, exist_ok=True)
    target = extension_target(root)

    if not SOURCE.is_dir():
        raise RuntimeError(f"Missing Project Forge VS Code extension source: {SOURCE}")

    existing = status(root)
    if existing["status"] == "files-present":
        return existing

    with tempfile.TemporaryDirectory(prefix="project-forge-vscode-", dir=str(root)) as tmp:
        staged = Path(tmp) / target.name
        shutil.copytree(SOURCE, staged)
        if target.exists():
            shutil.rmtree(target)
        staged.rename(target)

    prefix = f"{extension_id}-"
    for candidate in root.iterdir():
        if candidate == target or not candidate.is_dir() or not candidate.name.startswith(prefix):
            continue
        shutil.rmtree(candidate)

    result = status(root)
    result["reloadRequired"] = True
    return result


def uninstall(root: Path) -> dict[str, Any]:
    extension_id, version = extension_identity()
    prefix = f"{extension_id}-"
    removed: list[str] = []
    if root.exists():
        for candidate in root.iterdir():
            if candidate.is_dir() and candidate.name.startswith(prefix):
                shutil.rmtree(candidate)
                removed.append(str(candidate))
    return {
        "extensionId": extension_id,
        "version": version,
        "status": "not-installed",
        "removed": removed,
        "reloadRequired": bool(removed),
        "activationStatus": "not-applicable",
        "activationVerified": False,
        "verificationRequired": False,
    }


def emit(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, sort_keys=True))
        return
    print(f"Project Forge Work Item Status: {result['status'].upper()}")
    print(f"Extension: {result['extensionId']}@{result['version']}")
    if result.get("path"):
        print(f"Path: {result['path']}")
    if result.get("extensionsRootSource"):
        print(f"Extensions root: {result['extensionsRootSource']}")
    if result.get("removed"):
        print(f"Removed: {len(result['removed'])}")
    if result.get("verificationRequired"):
        print("Extension files are present; VS Code host discovery/activation is not verified by this installer.")
    if result.get("reloadRequired"):
        print("Reload VS Code to activate the changed extension installation.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install or inspect the optional Project Forge VS Code work-item status decorator."
    )
    parser.add_argument("action", choices=["status", "install", "uninstall"])
    parser.add_argument("--extensions-dir", type=Path, help="Override the VS Code extensions directory.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        root, root_source = resolve_extensions_root(args.extensions_dir)
        root = root.resolve()
        if args.action == "install":
            result = install(root)
        elif args.action == "uninstall":
            result = uninstall(root)
        else:
            result = status(root)
        result["extensionsRootSource"] = root_source
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        if args.json:
            print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        else:
            print(f"Project Forge Work Item Status: ERROR — {exc}", file=sys.stderr)
        return 1

    emit(result, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
