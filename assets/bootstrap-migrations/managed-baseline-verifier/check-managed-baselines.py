#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]


def read_json(name: str) -> dict:
    path = ROOT / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Unable to read {name}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} must contain a JSON object")
    return value


def safe_relative(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{label} must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise RuntimeError(f"Unsafe {label}: {value}")
    return normalized


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_component_metadata(component: str, metadata: dict, schema_version: int) -> dict:
    if schema_version == 1:
        result = {
            "revision": metadata.get("commit"),
            "distribution": metadata.get("distribution"),
        }
        if component == "core":
            result["version"] = metadata.get("version")
        return result
    if schema_version == 2:
        result = {
            "revision": metadata.get("revision"),
            "distribution": metadata.get("distribution"),
        }
        if component == "core":
            result["version"] = metadata.get("version")
        return result
    raise RuntimeError("Unsupported PROJECT_FORGE_BASELINE.json schemaVersion")


def component_baseline_metadata(component: str, baseline: dict, filename: str) -> dict:
    schema_version = baseline.get("schemaVersion")
    if schema_version == 1:
        if component == "core":
            return {
                "revision": baseline.get("coreCommit"),
                "version": baseline.get("coreVersion"),
                "distribution": baseline.get("distribution"),
            }
        if component == "deployment":
            return {
                "revision": baseline.get("deploymentKitCommit"),
                "distribution": baseline.get("distribution"),
            }
    elif schema_version == 2:
        if baseline.get("component") != component:
            raise RuntimeError(f"{filename} component does not match PROJECT_FORGE_BASELINE.json")
        result = {
            "revision": baseline.get("revision"),
            "distribution": baseline.get("distribution"),
        }
        if component == "core":
            result["version"] = baseline.get("version")
        return result
    else:
        raise RuntimeError(f"Unsupported {filename} schemaVersion")
    raise RuntimeError(f"Unsupported Project Forge component in generated baseline: {component}")


def validate_component(
    component: str,
    project_forge_component: dict,
    filename: str,
    project_schema_version: int,
) -> int:
    baseline = read_json(filename)
    if baseline.get("schemaVersion") != project_schema_version:
        raise RuntimeError(
            f"{filename} schemaVersion does not match PROJECT_FORGE_BASELINE.json"
        )

    expected = project_component_metadata(component, project_forge_component, project_schema_version)
    actual = component_baseline_metadata(component, baseline, filename)
    for key, expected_value in expected.items():
        if expected_value is not None and actual.get(key) != expected_value:
            raise RuntimeError(
                f"{filename} {key} does not match PROJECT_FORGE_BASELINE.json"
            )

    managed = baseline.get("managedPaths")
    if not isinstance(managed, list) or not managed:
        raise RuntimeError(f"{filename} managedPaths is missing or empty")

    count = 0
    seen: set[str] = set()
    for item in managed:
        if not isinstance(item, dict):
            raise RuntimeError(f"Invalid managedPaths entry in {filename}")
        relative = safe_relative(item.get("path"), f"{filename} managed path")
        expected_hash = item.get("sha256")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise RuntimeError(f"Invalid managed hash in {filename}: {relative}")
        if relative in seen:
            raise RuntimeError(f"Duplicate managed path in {filename}: {relative}")
        seen.add(relative)
        path = ROOT.joinpath(*PurePosixPath(relative).parts)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"Managed file missing or unsafe: {relative}")
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            raise RuntimeError(f"Managed file drift: {relative}")
        count += 1
    return count


def main() -> int:
    try:
        manifest = read_json("PROJECT_BOOTSTRAP.json")
        approved = (manifest.get("generation") or {}).get("project-forge") or {}
        project_forge = read_json("PROJECT_FORGE_BASELINE.json")
        project_schema_version = project_forge.get("schemaVersion")
        if project_schema_version not in {1, 2}:
            raise RuntimeError("Unsupported PROJECT_FORGE_BASELINE.json schemaVersion")
        for key in ["package", "version", "profile"]:
            if project_forge.get(key) != approved.get(key):
                raise RuntimeError(
                    f"PROJECT_FORGE_BASELINE.json {key} does not match PROJECT_BOOTSTRAP.json"
                )

        components = project_forge.get("components")
        if not isinstance(components, dict) or not components:
            raise RuntimeError("PROJECT_FORGE_BASELINE.json components is missing or empty")

        total = 0
        for component, metadata in sorted(components.items()):
            if component == "core":
                filename = "CORE_BASELINE.json"
            elif component == "deployment":
                filename = "DEPLOYMENT_BASELINE.json"
            else:
                raise RuntimeError(f"Unsupported Project Forge component: {component}")
            if not isinstance(metadata, dict):
                raise RuntimeError(f"Invalid Project Forge component metadata: {component}")
            total += validate_component(
                component,
                metadata,
                filename,
                project_schema_version,
            )
            print(f"PASS {filename}")

        print(f"PASS Project Forge managed baselines ({total} files)")
        return 0
    except RuntimeError as exc:
        print(f"FAIL Project Forge managed baselines: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
