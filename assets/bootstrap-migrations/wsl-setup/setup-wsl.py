#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "DEV_ENVIRONMENT.json"
CATALOG = ROOT / "tools" / "dev-environment" / "catalog"


class SetupError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SetupError(f"Missing required file: {path}") from exc


def run(args: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
        check=False,
    )


def is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").lower()
    except OSError:
        return False
    return "microsoft" in release or "wsl" in release


def command_path(command: str) -> str | None:
    return shutil.which(command)


def version_ok(spec: dict[str, Any], version: str | None) -> tuple[bool, str]:
    command = spec["command"]
    if not command_path(command):
        return False, "missing"
    result = run([command, *spec.get("verifyArgs", [])])
    detail = "\n".join(filter(None, [(result.stdout or "").strip(), (result.stderr or "").strip()]))
    if result.returncode != 0:
        return False, detail or f"exit {result.returncode}"
    if not version:
        return True, detail

    handler = spec.get("handler")
    if handler == "major-version":
        found = re.search(r"(\d+)\.", detail)
        return bool(found and found.group(1) == version.split(".")[0]), detail
    if handler == "java-major":
        found = re.search(r'(?:(?:version|openjdk)\s+\")?(\d+)', detail, flags=re.IGNORECASE)
        return bool(found and found.group(1) == version.split(".")[0]), detail
    return version in detail, detail


def ensure_apt_package(package: str) -> None:
    if run(["dpkg", "-s", package]).returncode == 0:
        return
    result = run(["sudo", "apt-get", "update"], capture=False)
    if result.returncode != 0:
        raise SetupError("apt-get update failed; rerun from an interactive WSL terminal with sudo access")
    result = run(["sudo", "apt-get", "install", "-y", package], capture=False)
    if result.returncode != 0:
        raise SetupError(f"Unable to install required Ubuntu package: {package}")


def ensure_fnm_node(version: str | None, check_only: bool) -> tuple[bool, str, str]:
    if not command_path("fnm"):
        return False, "fnm is missing in WSL; install fnm inside the distro before rerunning /setup", "MISSING"
    if not version:
        return True, "fnm available", "PASS"
    result = run(["fnm", "exec", f"--using={version}", "--", "node", "--version"])
    detail = "\n".join(filter(None, [(result.stdout or "").strip(), (result.stderr or "").strip()]))
    if result.returncode == 0 and version in detail.lstrip("v"):
        return True, detail, "PASS"
    if check_only:
        return False, detail or f"Node {version} is not installed through fnm", "VERSION_MISMATCH"
    install = run(["fnm", "install", version], capture=False)
    if install.returncode != 0:
        return False, f"fnm failed to install Node {version}", "FAILED"
    run(["fnm", "default", version], capture=False)
    verify = run(["fnm", "exec", f"--using={version}", "--", "node", "--version"])
    text = (verify.stdout or verify.stderr or "").strip()
    return verify.returncode == 0 and version in text.lstrip("v"), text, "PASS" if verify.returncode == 0 else "FAILED"


def ensure_tool(entry: dict[str, Any], check_only: bool) -> tuple[bool, str, str]:
    tool_id = entry["id"]
    spec = read_json(CATALOG / f"{tool_id}.json")
    version = entry.get("version")

    if tool_id == "node":
        return ensure_fnm_node(version, check_only)

    ok, detail = version_ok(spec, version)
    if ok:
        if tool_id == "docker":
            operational = run(["docker", "info", "--format", "{{.ServerVersion}}"])
            operational_detail = (operational.stdout or operational.stderr or "").strip()
            if operational.returncode != 0:
                return False, (
                    "Docker CLI is present but Docker Desktop is not operational through WSL integration. "
                    "Start Docker Desktop and enable this distro under Settings > Resources > WSL Integration. "
                    "Do not install a second Docker Engine inside WSL."
                ), "NOT_OPERATIONAL"
            return True, operational_detail, "PASS"
        return True, detail, "PASS"

    if check_only:
        return False, detail, "MISSING" if detail == "missing" else "VERSION_MISMATCH"

    apt_packages = {
        "git": "git",
        "github-cli": "gh",
        "python": "python3",
        "sqlite": "sqlite3",
        "ssh": "openssh-client",
        "go": "golang-go",
    }
    if tool_id in apt_packages:
        ensure_apt_package(apt_packages[tool_id])
        ok, detail = version_ok(spec, version)
        return ok, detail, "PASS" if ok else "FAILED"

    if tool_id == "vscode":
        return False, (
            "VS Code's WSL command bridge is unavailable. Install VS Code on Windows and the "
            "Remote - WSL extension, then open this repository with `code .` from WSL."
        ), "MISSING"
    if tool_id == "docker":
        return False, (
            "Docker is unavailable inside WSL. Install/start Docker Desktop on Windows and enable "
            "WSL integration for this distro; do not install Docker Engine inside WSL."
        ), "MISSING"
    if tool_id == "fnm":
        return False, (
            "fnm is required inside WSL for Project-declared Node versions. Install fnm in this "
            "distro, then rerun /setup."
        ), "MISSING"
    if tool_id == "dotnet":
        return False, (
            f".NET SDK {version or ''} is required inside WSL. Install the matching Microsoft .NET SDK "
            "for Ubuntu in this distro, then rerun /setup."
        ).strip(), "MISSING" if detail == "missing" else "VERSION_MISMATCH"
    if tool_id == "java":
        return False, (
            f"Java {version or ''} is required inside WSL. Install the matching JDK in this distro, "
            "then rerun /setup."
        ).strip(), "MISSING" if detail == "missing" else "VERSION_MISMATCH"

    return False, detail or f"No WSL installer is defined for {tool_id}", "MISSING"


def ensure_extensions(extensions: list[str], check_only: bool) -> list[str]:
    if not extensions or not command_path("code"):
        return extensions if not command_path("code") else []
    result = run(["code", "--list-extensions"])
    installed = {line.strip().lower() for line in (result.stdout or "").splitlines() if line.strip()}
    missing = [value for value in extensions if value.lower() not in installed]
    if not check_only:
        for extension in missing:
            run(["code", "--install-extension", extension, "--force"], capture=False)
        result = run(["code", "--list-extensions"])
        installed = {line.strip().lower() for line in (result.stdout or "").splitlines() if line.strip()}
        missing = [value for value in extensions if value.lower() not in installed]
    return missing


def restore_project(commands: list[list[str]], check_only: bool) -> list[str]:
    if check_only:
        return []
    plan_path = ROOT / "SCAFFOLD_PLAN.json"
    if plan_path.exists():
        plan = read_json(plan_path)
        missing_markers = [marker for marker in plan.get("markers", []) if not (ROOT / marker).exists()]
        if missing_markers:
            print("DEFERRED project restore — scaffold markers are not present")
            return []
    failures: list[str] = []
    for command in commands:
        if not command:
            continue
        result = run(command, capture=False)
        if result.returncode != 0:
            failures.append(" ".join(command))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare/verify a Project Forge developer environment in WSL2")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()

    if not is_wsl():
        raise SetupError("This Linux setup runtime is supported only inside WSL2 for the current Windows development profile.")
    if str(ROOT).startswith("/mnt/"):
        raise SetupError(
            "This Project is under a Windows-mounted filesystem. Project Forge's Windows default requires "
            "a Linux-native WSL checkout such as ~/projects/<repo>. Migrate the repository first."
        )

    config = read_json(CONFIG)
    declared = set(config.get("platforms", []))
    if not ({"windows", "linux"} & declared):
        raise SetupError("This Project does not declare a Windows/WSL-compatible development environment")

    print(f"== Developer environment (WSL2: {os.environ.get('WSL_DISTRO_NAME', 'Linux')}) ==")
    failed_required: list[str] = []
    failed_optional: list[str] = []
    for entry in config.get("tools", []):
        required = entry.get("required", True)
        ok, detail, state = ensure_tool(entry, args.check)
        version = f" {entry['version']}" if entry.get("version") else ""
        first = detail.splitlines()[0] if detail else ""
        print(f"{state} {entry['id']}{version}" + (f" — {first}" if first else ""))
        if not ok:
            (failed_required if required else failed_optional).append(entry["id"])

    missing_extensions = ensure_extensions(config.get("vscodeExtensions", []), args.check)
    for extension in missing_extensions:
        print(f"MISSING extension {extension}")
    if missing_extensions:
        failed_required.append("VS Code extensions")

    restore_failures = restore_project(config.get("projectRestore", []), args.check) if args.restore else []
    if restore_failures:
        failed_required.append("project restore")

    if failed_optional:
        print("Optional tools not ready: " + ", ".join(failed_optional))
    if failed_required:
        print("Required environment items not ready: " + ", ".join(failed_required), file=sys.stderr)
        return 2

    print("Project Forge WSL2 setup: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SetupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
