#!/usr/bin/env python3
"""Project Forge catalog-bound workstation updates. Status/preview never mutate."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

TOOL_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
VERSION = re.compile(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)")
PACKAGE_ID = re.compile(r"^[a-zA-Z0-9_.@/+:-]+$")
# Catalog identities alone do not authorize broad workstation upgrades.
SAFE_MANAGER_UPDATE_IDS = frozenset({"rtk", "github-cli", "git", "fnm"})


def platform() -> str:
    return "windows" if sys.platform == "win32" else "macos" if sys.platform == "darwin" else "linux" if sys.platform.startswith("linux") else "unsupported"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def run(argv: list[str], timeout: int = 15) -> tuple[int, str]:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=timeout, check=False)
        return result.returncode, (result.stdout + "\n" + result.stderr).strip()[:1000]
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, type(error).__name__


def semver(s: str | None) -> tuple[int, int, int] | None:
    match = VERSION.search(s or "")
    return tuple(map(int, match.group(1).split("."))) if match else None


def inventory(root: Path) -> list[dict]:
    env = load(root / "DEV_ENVIRONMENT.json")
    if env.get("schemaVersion") != 1:
        raise ValueError("unsupported DEV_ENVIRONMENT.json schema")
    values: list[dict] = []
    seen = set()
    for item in env.get("tools", []):
        name = item.get("id")
        if not isinstance(name, str) or not TOOL_ID.fullmatch(name) or name in seen:
            raise ValueError(f"unsafe or duplicate declared tool: {name}")
        seen.add(name)
        src = root / "tools/dev-environment/catalog" / (name + ".json")
        if not src.is_file():
            values.append({"id": name, "status": "CATALOG_MISSING", "update": "MANUAL_REVIEW"})
            continue
        data = load(src)
        if data.get("id") != name:
            raise ValueError(f"tool catalog identity mismatch: {name}")
        executable = data.get("command")
        verify = data.get("verifyArgs", ["--version"])
        if not isinstance(executable, str) or not isinstance(verify, list) or not all(isinstance(v, str) for v in verify):
            raise ValueError(f"invalid verification command for {name}")
        path = shutil.which(executable)
        rc, output = run([path, *verify]) if path else (127, "")
        installed = semver(output) if rc == 0 else None
        spec = data.get("install", {}).get(platform(), {})
        spec = spec if isinstance(spec, dict) else {}
        manager = spec.get("manager")
        package = spec.get("package")
        pin = item.get("version")
        update = "MANUAL_REVIEW"
        if pin:
            update = "PROJECT_PINNED"
        elif (rc == 0 and name in SAFE_MANAGER_UPDATE_IDS and
              data.get("category") in ("machine-tool", "runtime-manager") and
              manager in ("winget", "brew") and isinstance(package, str) and PACKAGE_ID.fullmatch(package)):
            update = "MANAGER_CHECK"
        elif rc == 0 and manager == "project-forge-pinned-release":
            expected = semver(spec.get("version"))
            update = "APPROVED_PIN_CURRENT" if installed == expected and expected else (
                "PINNED_RELEASE_UPGRADE" if installed and expected and installed < expected and name == "rtk" else "MANUAL_REVIEW"
            )
        values.append({"id": name, "status": "INSTALLED" if rc == 0 else "NOT_INSTALLED",
                       "installedVersion": ".".join(map(str, installed)) if installed else None,
                       "projectPin": pin, "update": update, "manager": manager, "package": package,
                       "approvedVersion": spec.get("version") if manager == "project-forge-pinned-release" else None})
    return values


def make_plan(root: Path, selected: list[str]) -> dict:
    items = inventory(root)
    candidates = {x["id"]: x for x in items}
    if not selected:
        selected = [v["id"] for v in items if v["update"] in ("MANAGER_CHECK", "PINNED_RELEASE_UPGRADE")]
    if len(selected) != len(set(selected)):
        raise ValueError("duplicate requested tool")
    ops = []
    for name in sorted(selected):
        if name not in candidates:
            raise ValueError(f"undeclared tool {name}")
        item = candidates[name]
        if item["update"] == "MANAGER_CHECK":
            manager = item["manager"]
            if not shutil.which(manager):
                raise ValueError(f"package manager {manager} is missing")
            cmd = ["brew", "upgrade", item["package"]] if manager == "brew" else [
                "winget", "upgrade", "--id", item["package"], "--exact",
                "--accept-source-agreements", "--accept-package-agreements"
            ]
        elif item["update"] == "PINNED_RELEASE_UPGRADE":
            launcher = root / "scripts/setup.sh"
            if platform() != "linux" or not launcher.is_file() or "--update-rtk" not in launcher.read_text(encoding="utf-8"):
                raise ValueError("approved pinned RTK update launcher unavailable; use an updated Bootstrap setup script")
            cmd = ["bash", str(launcher), "--update-rtk"]
        else:
            raise ValueError(f"{name} cannot be automatically updated: {item['update']}")
        ops.append({"id": name, "command": cmd, "fromVersion": item["installedVersion"],
                    "approvedVersion": item["approvedVersion"]})
    plan = {"schemaVersion": 1, "platform": platform(), "operations": ops}
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"plan": plan, "sha256": digest}


def _marker_payload() -> str:
    return json.dumps({"checkedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat()}) + "\n"


def _marker_read_value(handle) -> str | None:
    value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("expected object in setup maintenance marker")
    return value.get("checkedAtUtc")


def _posix_marker_check(root: Path, record: bool) -> str | None:
    """Use directory handles and O_NOFOLLOW throughout: no path-based write races."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as closing:
        parent = os.open(root, flags)
        closing.callback(os.close, parent)
        for name in (".project-forge", "setup-maintenance"):
            try:
                child = os.open(name, flags, dir_fd=parent)
            except FileNotFoundError:
                if not record:
                    return None
                try:
                    os.mkdir(name, 0o700, dir_fd=parent)
                except FileExistsError:
                    pass
                try:
                    child = os.open(name, flags, dir_fd=parent)
                except OSError as error:
                    raise ValueError(
                        f"unsafe setup maintenance marker directory: {name} (symlink or non-directory)"
                    ) from error
            except OSError as error:
                raise ValueError(
                    f"unsafe setup maintenance marker directory: {name} (symlink or non-directory)"
                ) from error
            closing.callback(os.close, child)
            parent = child

        name = "last-check.json"
        try:
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            info = None
        if info is not None and not stat.S_ISREG(info.st_mode):
            raise ValueError("unsafe setup maintenance marker file: symlink or non-regular file")

        previous = None
        if info is not None:
            # Re-open through the pinned directory handle and check the final
            # inode too, so a swapped symlink or special file cannot be read.
            with os.fdopen(
                os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent),
                "r", encoding="utf-8"
            ) as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise ValueError("unsafe setup maintenance marker file: non-regular file")
                previous = _marker_read_value(handle)

        if record:
            # Atomic replacement instead of truncating the existing inode:
            # neither a symlink nor a hard link can redirect the marker write.
            temporary = f".last-check-{secrets.token_hex(12)}.tmp"
            created = False
            try:
                fd = os.open(
                    temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600, dir_fd=parent
                )
                created = True
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(_marker_payload())
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                created = False
            finally:
                if created:
                    os.unlink(temporary, dir_fd=parent)
        return previous


def _windows_marker_component(path: Path, *, directory: bool) -> os.stat_result | None:
    """Refuse symlinks, junctions and other Windows reparse points."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        or (directory and not stat.S_ISDIR(info.st_mode))
        or (not directory and not stat.S_ISREG(info.st_mode))
    ):
        raise ValueError(f"unsafe setup maintenance marker path: symlink, reparse point or unexpected type at {path}")
    return info


def _windows_marker_check(root: Path, record: bool) -> str | None:
    """Conservative native Windows checks with an atomic final-file replacement.

    Native Windows Python has no POSIX dir_fd/O_NOFOLLOW operations. Check each
    component for reparse points, retain its identity, and recheck before the
    final atomic replace. Never use write_text() on the destination.
    """
    parent = root
    identities = []
    for name in (".project-forge", "setup-maintenance"):
        parent = parent / name
        info = _windows_marker_component(parent, directory=True)
        if info is None:
            if not record:
                return None
            try:
                parent.mkdir(mode=0o700)
            except FileExistsError:
                pass
            info = _windows_marker_component(parent, directory=True)
            if info is None:
                raise ValueError(f"unable to establish safe setup maintenance directory: {parent}")
        identities.append((parent, info.st_dev, info.st_ino))

    marker = parent / "last-check.json"
    existing = _windows_marker_component(marker, directory=False)
    previous = None
    if existing is not None:
        with marker.open("r", encoding="utf-8") as handle:
            previous = _marker_read_value(handle)
    if record:
        fd, tmp = tempfile.mkstemp(prefix=".last-check-", suffix=".tmp", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(_marker_payload())
                handle.flush()
                os.fsync(handle.fileno())
            for directory, dev, ino in identities:
                current = _windows_marker_component(directory, directory=True)
                if current is None or (current.st_dev, current.st_ino) != (dev, ino):
                    raise ValueError(f"unsafe setup maintenance directory changed before marker replacement: {directory}")
            _windows_marker_component(marker, directory=False)
            os.replace(tmp, marker)
        finally:
            if os.path.lexists(tmp):
                os.unlink(tmp)
    return previous


def marker_check(root: Path, *, record: bool) -> str | None:
    """Read and optionally store a check timestamp only in a safe checkout path."""
    return _windows_marker_check(root, record) if os.name == "nt" else _posix_marker_check(root, record)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "update"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--tool", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--plan-sha256")
    parser.add_argument("--record-check", action="store_true")
    args = parser.parse_args()
    if args.action == "status" and (args.tool or args.apply or args.plan_sha256):
        parser.error("status is read-only and cannot accept update controls")
    if args.action == "update" and args.record_check:
        parser.error("--record-check applies only to status")
    if args.apply != bool(args.plan_sha256):
        parser.error("apply requires a reviewed --plan-sha256 and vice versa")
    root = args.root.resolve()
    try:
        if args.action == "status":
            result = {"platform": platform(), "tools": inventory(root)}
            previous = marker_check(root, record=args.record_check)
            if previous is not None:
                result["previousCheckUtc"] = previous
            print(json.dumps(result, indent=2))
            return 0
        result = make_plan(root, args.tool)
        if not args.apply:
            print(json.dumps({"mode": "PREVIEW", **result}, indent=2))
            return 0
        if args.plan_sha256 != result["sha256"]:
            raise ValueError("update plan changed; re-preview and reapprove")
        applied = []
        for op in result["plan"]["operations"]:
            code, _ = run(op["command"], timeout=900)
            applied.append({"id": op["id"], "exitCode": code})
            if code:
                print(json.dumps({"mode": "PARTIAL_FAILURE", "applied": applied}, indent=2))
                return 2
        print(json.dumps({"mode": "APPLIED", "applied": applied, "after": inventory(root)}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
