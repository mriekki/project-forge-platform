#!/usr/bin/env python3
"""Explicit, non-secret cross-workstation Household Registry locator.

Stores URL + stable Registry instance fingerprint in a protected local file.
This does not authenticate a Developer, read the Household database, install
OAuth clients or grant cross-Project access. Each Developer still signs in with
Google and is independently invited by the household administrator.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

HEX32 = re.compile(r"^[0-9a-f]{32}$")


class ConnectionError(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def validate_origin(origin: str) -> str:
    if not isinstance(origin, str) or len(origin) > 254:
        raise ConnectionError("Registry locator must be an exact HTTPS origin.")
    parsed = urlparse(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or \
       parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ConnectionError("Registry locator must be an exact HTTPS origin.")
    if parsed.hostname.lower() == "localhost" or parsed.hostname.startswith("127."):
        raise ConnectionError("Registry locator must use a verified public TLS name.")
    return origin.rstrip("/")


def probe(origin: str) -> dict:
    origin = validate_origin(origin)
    url = origin + "/.well-known/project-forge-household"
    opener = urllib.request.build_opener(NoRedirect())
    req = urllib.request.Request(url, headers={"Accept":"application/json"}, method="GET")
    try:
        with opener.open(req, timeout=10) as response:
            if response.status != 200 or response.url != url:
                raise ConnectionError("Registry discovery did not return an exact trusted origin.")
            raw = response.read(8193)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        raise ConnectionError("Registry discovery is unavailable; do not assume existing Projects are offline.") from error
    if len(raw) > 8192:
        raise ConnectionError("Registry discovery response exceeds safe bounds.")
    try:
        obj = json.loads(raw)
    except (UnicodeError, ValueError) as error:
        raise ConnectionError("Registry discovery is not valid JSON.") from error
    if not isinstance(obj, dict) or obj.get("schemaVersion") != 1 or \
       obj.get("service") != "project-forge-household-registry" or \
       obj.get("authentication") != "google-oidc" or \
       not isinstance(obj.get("instanceId"), str) or not HEX32.fullmatch(obj["instanceId"]):
        raise ConnectionError("Registry discovery does not match the supported contract.")
    needed = {"member-directory", "resource-inventory", "project-registry"}
    if not isinstance(obj.get("capabilities"), list) or \
       not needed.issubset(set(x for x in obj["capabilities"] if isinstance(x, str))):
        raise ConnectionError("Registry discovery lacks required capabilities.")
    return {"schemaVersion":1, "kind":"project-forge-household-connection",
            "registryOrigin":origin, "instanceId":obj["instanceId"]}


def default_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "ProjectForge"
    else:
        base = Path.home() / ".config" / "project-forge"
    return base / "household.json"


def connect(origin: str, location: Path) -> dict:
    connection = probe(origin)
    if location.is_file():
        try:
            saved = json.loads(location.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ConnectionError("Existing connection is damaged; manual review required.") from error
        if saved != connection:
            raise ConnectionError("Registry identity changed; manual review required before reconnecting.")
        return connection
    if not location.parent.is_dir():
        raise ConnectionError("Create and protect the local connection directory before setup.")
    try:
        fd = os.open(location, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(connection, stream, sort_keys=True, indent=2)
            stream.write("\n")
    except OSError as error:
        raise ConnectionError("Unable to create a non-overwriting connection locator.") from error
    return connection


def doctor(location: Path) -> dict:
    if not location.is_file() or location.stat().st_size > 4096:
        raise ConnectionError("Household connection locator is missing or invalid.")
    try:
        stored = json.loads(location.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        raise ConnectionError("Household connection locator cannot be read.") from error
    if not isinstance(stored, dict) or set(stored) != {
        "schemaVersion", "kind", "registryOrigin", "instanceId"}:
        raise ConnectionError("Household connection schema is not recognized.")
    found = probe(stored["registryOrigin"])
    if found != stored:
        raise ConnectionError("Registry identity changed; block automatic adoption.")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Connect a workstation to an existing Project Forge Household Registry")
    parser.add_argument("command", choices=["connect", "doctor"])
    parser.add_argument("--registry-origin", help="Explicit administrator-confirmed HTTPS Registry URL")
    parser.add_argument("--connection-file", type=Path, default=default_path())
    args = parser.parse_args(argv)
    try:
        if args.command == "connect":
            if not args.registry_origin:
                raise ConnectionError("Explicit Registry origin is required.")
            state = connect(args.registry_origin, args.connection_file)
        else:
            state = doctor(args.connection_file)
    except (ConnectionError, OSError) as error:
        print("BLOCKED: " + str(error), file=sys.stderr)
        return 2
    print("Registry connection verified: " + state["registryOrigin"])
    print("Instance fingerprint: " + state["instanceId"])
    print("Google sign-in and an explicit household invitation are still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
