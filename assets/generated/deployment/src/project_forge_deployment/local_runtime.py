"""Loopback-only immutable application deployment on the developer workstation."""

from __future__ import annotations

import hashlib
import json
import socket
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from .app_runtime import PRODUCTION_APP_DEPLOY_WRITE_PHRASE, normalize_app_spec
from .errors import DeploymentKitError
from .local_extensions import bindings, normalize_bindings, normalize_mounts, snapshot_material
from .profiles import config_root

LOCAL_RUNTIME_SCHEMA_VERSION = 1
LOCAL_APP_DEPLOY_WRITE_PHRASE = "[LOCAL APP DEPLOY]"
LOOPBACK_ADDRESS = "127.0.0.1"

_LABEL_PREFIX = "com.mriekki.project-forge"
_LABEL_OWNER = f"{_LABEL_PREFIX}.owner-repo"
_LABEL_APP = f"{_LABEL_PREFIX}.app-slug"
_LABEL_ENV = f"{_LABEL_PREFIX}.environment"
_LABEL_SPEC = f"{_LABEL_PREFIX}.spec-sha256"
_LABEL_PLACEMENT = f"{_LABEL_PREFIX}.placement"


def _docker() -> str:
    executable = shutil.which("docker")
    if not executable:
        raise DeploymentKitError(
            "Docker is unavailable. Workstation-container deployment requires a working Docker CLI/engine."
        )
    completed = subprocess.run(
        [executable, "info", "--format", "{{.ServerVersion}}"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise DeploymentKitError("Docker engine is not ready" + (f": {detail}" if detail else "."))
    return executable


def _run(docker: str, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [docker, *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip() or f"exit {completed.returncode}"
        raise DeploymentKitError(f"Local Docker command failed: {detail}")
    return completed


def _host_port(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 65535:
        raise DeploymentKitError("hostPort must be an integer from 1 through 65535.")
    return value


def _state_root(app_slug: str, environment: str) -> Path:
    return config_root() / "local-apps" / app_slug / environment


def _state_file(app_slug: str, environment: str) -> Path:
    return _state_root(app_slug, environment) / "deployment.json"


def _evidence_file(app_slug: str, environment: str) -> Path:
    return _state_root(app_slug, environment) / "deployment-evidence.jsonl"


def _data_dir(app_slug: str, environment: str) -> Path:
    return _state_root(app_slug, environment) / "data"


def _safe_state_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _append_evidence(app_slug: str, environment: str, value: dict[str, Any]) -> None:
    path = _evidence_file(app_slug, environment)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as target:
        target.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _load_state(app_slug: str, environment: str) -> dict[str, Any] | None:
    path = _state_file(app_slug, environment)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DeploymentKitError(f"Cannot read local deployment state {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schemaVersion") not in (1, 2):
        raise DeploymentKitError(f"Unsupported local deployment state: {path}")
    return value


def normalize_local_spec(
    *,
    owner_repo: str,
    environment: str,
    app_slug: str,
    container_name: str,
    image: str,
    runtime_port: int,
    host_port: int,
    health_path: str,
    run_as: str,
    persistence_mode: str,
    data_container_path: str | None,
    environment_variables: dict[str, str] | Iterable[tuple[str, str]],
    additional_port_bindings: list[dict[str, int]] | None = None,
    read_only_mounts: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    base = normalize_app_spec(
        owner_repo=owner_repo,
        environment=environment,
        app_slug=app_slug,
        container_name=container_name,
        image=image,
        runtime_port=runtime_port,
        health_path=health_path,
        run_as=run_as,
        persistence_mode=persistence_mode,
        data_container_path=data_container_path,
        environment_variables=environment_variables,
    )
    base.pop("specSha256", None)
    base.update(
        {
            "schemaVersion": LOCAL_RUNTIME_SCHEMA_VERSION,
            "placement": "workstation",
            "isolation": "container",
            "exposure": "loopback",
            "hostAddress": LOOPBACK_ADDRESS,
            "hostPort": _host_port(host_port),
        }
    )
    extra_bindings = normalize_bindings(base["hostPort"], base["runtimePort"], additional_port_bindings or [])
    extra_mounts = normalize_mounts(base["appSlug"], base["environment"], read_only_mounts or [], base["persistence"]["dataContainerPath"])
    if extra_bindings:
        base["additionalPortBindings"] = extra_bindings
    if extra_mounts:
        base["readOnlyMounts"] = extra_mounts
    base["specSha256"] = hashlib.sha256(
        json.dumps(base, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return base


def _inspect_owned_container(docker: str, container_name: str) -> dict[str, Any] | None:
    inspected = _run(
        docker,
        [
            "inspect",
            "--format",
            "{{json .Config.Labels}}\t{{json .NetworkSettings.Ports}}\t{{.State.Running}}\t{{json .Mounts}}\t{{json .HostConfig.PortBindings}}",
            container_name,
        ],
        check=False,
    )
    if inspected.returncode != 0:
        detail = (inspected.stderr or "").lower()
        if "no such" in detail or "not found" in detail:
            return None
        raise DeploymentKitError(
            f"Unable to inspect local container {container_name}: {(inspected.stderr or inspected.stdout).strip()}"
        )
    parts = inspected.stdout.strip().split("\t")
    if len(parts) != 5:
        raise DeploymentKitError("Local Docker inspect returned malformed container evidence.")
    try:
        labels = json.loads(parts[0]) if parts[0] else {}
        ports = json.loads(parts[1]) if parts[1] else {}
        mounts = json.loads(parts[3]) if parts[3] else []
        host_bindings = json.loads(parts[4]) if parts[4] else {}
    except json.JSONDecodeError as error:
        raise DeploymentKitError("Local Docker inspect returned malformed JSON evidence.") from error
    if not isinstance(labels, dict):
        labels = {}
    return {
        "labels": labels,
        "ports": ports if isinstance(ports, dict) else {},
        "mounts": mounts if isinstance(mounts, list) else [],
        "hostBindings": host_bindings if isinstance(host_bindings, dict) else {},
        "running": parts[2].strip().lower() == "true",
    }


def _assert_owned_or_absent(
    docker: str,
    *,
    container_name: str,
    owner_repo: str,
    app_slug: str,
    environment: str,
) -> dict[str, Any] | None:
    existing = _inspect_owned_container(docker, container_name)
    if existing is None:
        return None
    labels = existing["labels"]
    identity = (labels.get(_LABEL_OWNER), labels.get(_LABEL_APP), labels.get(_LABEL_ENV))
    expected = (owner_repo, app_slug, environment)
    if identity != expected:
        raise DeploymentKitError(
            f"Container name '{container_name}' already exists but is not owned by "
            f"{owner_repo} / {app_slug} / {environment}; refusing replacement."
        )
    return existing


def _managed_containers(docker: str) -> list[dict[str, Any]]:
    listed = _run(
        docker,
        ["ps", "-a", "--filter", f"label={_LABEL_PLACEMENT}=workstation", "--format", "{{.Names}}"],
    )
    result: list[dict[str, Any]] = []
    for name in sorted(line.strip() for line in listed.stdout.splitlines() if line.strip()):
        info = _inspect_owned_container(docker, name)
        if info is None:
            continue
        labels = info["labels"]
        if not all(labels.get(key) for key in (_LABEL_OWNER, _LABEL_APP, _LABEL_ENV, _LABEL_SPEC)):
            continue
        result.append(
            {
                "containerName": name,
                "ownerRepo": labels[_LABEL_OWNER],
                "appSlug": labels[_LABEL_APP],
                "environment": labels[_LABEL_ENV],
                "specSha256": labels[_LABEL_SPEC],
                "running": info["running"],
                "actualPorts": info["ports"],
                "actualMounts": info["mounts"],
                "actualHostBindings": info["hostBindings"],
            }
        )
    return result


def _http_healthy(spec: dict[str, Any], *, timeout: float = 2.0) -> bool:
    url = f"http://{LOOPBACK_ADDRESS}:{spec['hostPort']}{spec['healthPath']}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 400
    except (OSError, urllib.error.URLError):
        return False



def _actual_bindings(raw: dict[str, Any]) -> list[dict[str, int | str]]:
    result: list[dict[str, int | str]] = []
    if not isinstance(raw, dict):
        raise DeploymentKitError("Invalid Docker port-binding evidence.")
    for container, hosts in raw.items():
        if hosts is None:
            continue  # Exposed internally, not published on the host.
        if not isinstance(hosts, list) or not container.endswith("/tcp"):
            raise DeploymentKitError("Unexpected Docker port protocol or malformed binding evidence.")
        try:
            runtime = int(container.removesuffix("/tcp"))
            for host in hosts:
                result.append({"hostAddress": host["HostIp"], "hostPort": int(host["HostPort"]), "runtimePort": runtime})
        except (KeyError, ValueError, TypeError) as error:
            raise DeploymentKitError("Invalid Docker port-binding evidence.") from error
    return sorted(result, key=lambda item: (item["hostPort"], item["runtimePort"]))


def _expected_bindings(state: dict[str, Any]) -> list[dict[str, int | str]]:
    return sorted(({"hostAddress": LOOPBACK_ADDRESS, **item} for item in bindings(state)),
                  key=lambda item: (item["hostPort"], item["runtimePort"]))


def _actual_mounts(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise DeploymentKitError("Invalid Docker mount evidence.")
    try:
        return sorted(({"source": item["Source"], "target": item["Destination"],
                        "readOnly": not item["RW"], "type": item["Type"]} for item in raw),
                      key=lambda item: (item["target"], item["source"]))
    except (KeyError, TypeError) as error:
        raise DeploymentKitError("Invalid Docker mount evidence.") from error


def _expected_mounts(state: dict[str, Any]) -> list[dict[str, Any]]:
    expected = [{"source": item["source"], "target": item["target"], "readOnly": True, "type": "bind"}
                for item in state.get("readOnlyMounts", [])]
    if state["persistence"]["mode"] == "directory":
        expected.append({"source": str(_data_dir(state["appSlug"], state["environment"]).resolve()),
                         "target": state["persistence"]["dataContainerPath"], "readOnly": False, "type": "bind"})
    return sorted(expected, key=lambda item: (item["target"], item["source"]))


def _config_drift(container: dict[str, Any], state: dict[str, Any] | None) -> bool:
    if not state or container["specSha256"] != state.get("specSha256"):
        return True
    try:
        actual = _actual_bindings(container["actualPorts"])
        host_config = _actual_bindings(container["actualHostBindings"])
        expected = _expected_bindings(state)
        live_bindings_match = actual == expected or (container["running"] is False and not actual)
        return (not live_bindings_match
                or host_config != expected
                or _actual_mounts(container["actualMounts"]) != _expected_mounts(state))
    except (DeploymentKitError, KeyError, TypeError, ValueError):
        return True


def _assert_bindable(ports: list[int], owned_ports: set[int]) -> None:
    for port in ports:
        if port in owned_ports:
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((LOOPBACK_ADDRESS, port))
        except OSError as error:
            raise DeploymentKitError(f"Loopback host port {port} is occupied or unavailable.") from error


def _preflight_material(docker: str, spec: dict[str, Any]) -> None:
    if not spec.get("readOnlyMounts"):
        return
    for mount in spec["readOnlyMounts"]:
        source = Path(mount["source"])
        checks: list[str] = []
        for path in [source, *sorted(source.rglob("*"))]:
            suffix = path.relative_to(source).as_posix()
            inside = mount["target"] if suffix == "." else mount["target"] + "/" + suffix
            checks.extend(["d:" + inside if path.is_dir() else "f:" + inside])
        args = ["run", "--rm", "--network", "none", "--read-only", "--pull", "never",
                "--user", spec["runAs"], "--mount",
                f"type=bind,source={mount['source']},target={mount['target']},readonly",
                "--entrypoint", "/bin/sh", spec["image"], "-c",
                'for item do path=${item#??}; case "$item" in d:*) [ -d "$path" ] && [ -r "$path" ] && [ -x "$path" ] ;; f:*) [ -f "$path" ] && [ -r "$path" ] ;; esac || exit 1; done',
                "--", *checks]
        result = _run(docker, args, check=False)
        if result.returncode != 0:
            raise DeploymentKitError(
                "Material preflight failed: configured container UID/GID cannot read approved material "
                "or the immutable image lacks /bin/sh. Existing runtime was not replaced."
            )


def local_inventory() -> dict[str, Any]:
    docker = _docker()
    applications: list[dict[str, Any]] = []
    for container in _managed_containers(docker):
        state = _load_state(container["appSlug"], container["environment"])
        item = dict(container)
        item.update(
            {
                "placement": "workstation",
                "isolation": "container",
                "exposure": "loopback",
                "hostAddress": LOOPBACK_ADDRESS,
                "hostPort": state.get("hostPort") if state else None,
                "image": state.get("image") if state else None,
                "runtimePort": state.get("runtimePort") if state else None,
                "healthPath": state.get("healthPath") if state else None,
                "httpHealthy": bool(state and container["running"] and _http_healthy(state)),
                "additionalPortBindings": state.get("additionalPortBindings", []) if state else [],
                "readOnlyMounts": state.get("readOnlyMounts", []) if state else [],
                "configurationDrift": _config_drift(container, state),
            }
        )
        applications.append(item)
    return {
        "schemaVersion": LOCAL_RUNTIME_SCHEMA_VERSION,
        "placement": "workstation",
        "isolation": "container",
        "exposure": "loopback",
        "applications": applications,
        "mutated": False,
    }


def _inventory_snapshot(inventory: dict[str, Any]) -> str:
    value = {
        "applications": [
            {
                key: item.get(key)
                for key in (
                    "containerName",
                    "ownerRepo",
                    "appSlug",
                    "environment",
                    "specSha256",
                    "running",
                    "hostPort",
                    "additionalPortBindings",
                    "readOnlyMounts",
                    "configurationDrift",
                )
            }
            for item in inventory["applications"]
        ]
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _assert_port_available(
    inventory: dict[str, Any], *, host_port: int, app_slug: str, environment: str
) -> None:
    for item in inventory["applications"]:
        owned = {item.get("hostPort")} | {mapping["hostPort"] for mapping in item.get("additionalPortBindings", [])}
        if host_port in owned and (item["appSlug"], item["environment"]) != (app_slug, environment):
            raise DeploymentKitError(
                f"Loopback host port {host_port} is already owned by "
                f"{item['appSlug']} / {item['environment']}."
            )


def plan_local_deploy(spec: dict[str, Any]) -> dict[str, Any]:
    docker = _docker()
    _assert_owned_or_absent(
        docker,
        container_name=spec["containerName"],
        owner_repo=spec["ownerRepo"],
        app_slug=spec["appSlug"],
        environment=spec["environment"],
    )
    inventory = local_inventory()
    for mapping in bindings(spec):
        _assert_port_available(
            inventory, host_port=mapping["hostPort"],
            app_slug=spec["appSlug"], environment=spec["environment"],
        )
    existing = next(
        (
            item
            for item in inventory["applications"]
            if item["appSlug"] == spec["appSlug"] and item["environment"] == spec["environment"]
        ),
        None,
    )
    if existing and existing["specSha256"] == spec["specSha256"] and existing["running"] and existing["httpHealthy"] and not existing.get("configurationDrift", True):
        raise DeploymentKitError("The exact local application runtime is already deployed and healthy.")
    return {
        "action": "deploy",
        "placement": "workstation",
        "isolation": "container",
        "exposure": "loopback",
        "publicExposure": False,
        "hostAddress": LOOPBACK_ADDRESS,
        "hostPort": spec["hostPort"],
        "environment": spec["environment"],
        "appSlug": spec["appSlug"],
        "ownerRepo": spec["ownerRepo"],
        "containerName": spec["containerName"],
        "image": spec["image"],
        "runtimePort": spec["runtimePort"],
        "healthPath": spec["healthPath"],
        "persistenceMode": spec["persistence"]["mode"],
        "changeType": "update" if existing else "create",
        "previousImage": existing.get("image") if existing else None,
        "inventorySnapshot": _inventory_snapshot(inventory),
        **({"materialSnapshot": snapshot_material(spec)} if spec.get("readOnlyMounts") else {}),
        **({"additionalPortBindings": spec["additionalPortBindings"]} if spec.get("additionalPortBindings") else {}),
        **({"readOnlyMounts": spec["readOnlyMounts"]} if spec.get("readOnlyMounts") else {}),
        "spec": spec,
    }


def local_deploy_write_phrase(plan: dict[str, Any]) -> str:
    return PRODUCTION_APP_DEPLOY_WRITE_PHRASE if plan["environment"] == "production" else LOCAL_APP_DEPLOY_WRITE_PHRASE


def _container_args(spec: dict[str, Any]) -> list[str]:
    args = [
        "run",
        "-d",
        "--name",
        spec["containerName"],
        "--restart",
        "unless-stopped",
        "--user",
        spec["runAs"],
        "-p",
        f"{LOOPBACK_ADDRESS}:{spec['hostPort']}:{spec['runtimePort']}",
        "--label",
        f"{_LABEL_OWNER}={spec['ownerRepo']}",
        "--label",
        f"{_LABEL_APP}={spec['appSlug']}",
        "--label",
        f"{_LABEL_ENV}={spec['environment']}",
        "--label",
        f"{_LABEL_SPEC}={spec['specSha256']}",
        "--label",
        f"{_LABEL_PLACEMENT}=workstation",
    ]
    for mapping in spec.get("additionalPortBindings", []):
        args.extend(["-p", f"{LOOPBACK_ADDRESS}:{mapping['hostPort']}:{mapping['runtimePort']}"])
    for mount in spec.get("readOnlyMounts", []):
        args.extend(["--mount", f"type=bind,source={mount['source']},target={mount['target']},readonly"])
    if spec["persistence"]["mode"] == "directory":
        data_dir = _data_dir(spec["appSlug"], spec["environment"]).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        args.extend(["-v", f"{data_dir}:{spec['persistence']['dataContainerPath']}"])
    for key, value in spec["environmentVariables"].items():
        args.extend(["-e", f"{key}={value}"])
    args.append(spec["image"])
    return args


def _wait_for_health(spec: dict[str, Any], *, timeout_seconds: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _http_healthy(spec):
            return
        time.sleep(1.0)
    raise DeploymentKitError(
        f"Local application failed loopback health check at "
        f"http://{LOOPBACK_ADDRESS}:{spec['hostPort']}{spec['healthPath']}."
    )


def _persist_state(spec: dict[str, Any]) -> None:
    value = {
        "schemaVersion": 2 if spec.get("additionalPortBindings") or spec.get("readOnlyMounts") else LOCAL_RUNTIME_SCHEMA_VERSION,
        **({"additionalPortBindings": spec["additionalPortBindings"]} if spec.get("additionalPortBindings") else {}),
        **({"readOnlyMounts": spec["readOnlyMounts"]} if spec.get("readOnlyMounts") else {}),
        "ownerRepo": spec["ownerRepo"],
        "appSlug": spec["appSlug"],
        "environment": spec["environment"],
        "containerName": spec["containerName"],
        "image": spec["image"],
        "specSha256": spec["specSha256"],
        "runtimePort": spec["runtimePort"],
        "hostPort": spec["hostPort"],
        "hostAddress": LOOPBACK_ADDRESS,
        "healthPath": spec["healthPath"],
        "runAs": spec["runAs"],
        "persistence": spec["persistence"],
        "placement": "workstation",
        "isolation": "container",
        "exposure": "loopback",
        "environmentVariableNames": sorted(spec["environmentVariables"]),
    }
    _safe_state_write(_state_file(spec["appSlug"], spec["environment"]), value)


def apply_local_deploy(plan: dict[str, Any]) -> dict[str, Any]:
    required = {
        "action",
        "placement",
        "isolation",
        "exposure",
        "publicExposure",
        "hostAddress",
        "hostPort",
        "environment",
        "appSlug",
        "ownerRepo",
        "containerName",
        "image",
        "runtimePort",
        "healthPath",
        "persistenceMode",
        "changeType",
        "previousImage",
        "inventorySnapshot",
        "spec",
    }
    if not isinstance(plan, dict):
        raise DeploymentKitError("Malformed local application deployment plan.")
    if plan.get("additionalPortBindings"):
        required.add("additionalPortBindings")
    if plan.get("readOnlyMounts"):
        required.update(("readOnlyMounts", "materialSnapshot"))
    if set(plan) != required or plan["action"] != "deploy":
        raise DeploymentKitError("Malformed local application deployment plan.")
    current = local_inventory()
    if _inventory_snapshot(current) != plan["inventorySnapshot"]:
        raise DeploymentKitError(
            "Local application inventory changed after plan review; create and authorize a fresh plan."
        )
    spec = plan["spec"]
    if plan.get("additionalPortBindings", []) != spec.get("additionalPortBindings", []) or plan.get("readOnlyMounts", []) != spec.get("readOnlyMounts", []):
        raise DeploymentKitError("Deployment plan options differ from the approved specification.")
    if plan.get("materialSnapshot") != snapshot_material(spec):
        raise DeploymentKitError("External material changed after review; approve a fresh deployment plan.")
    current_app = next((item for item in current["applications"]
                        if item["appSlug"] == spec["appSlug"] and item["environment"] == spec["environment"]), None)
    if current_app and current_app.get("configurationDrift", False):
        raise DeploymentKitError("Existing managed Docker runtime has configuration drift; do not replace it automatically.")
    for mapping in bindings(spec):
        _assert_port_available(current, host_port=mapping["hostPort"], app_slug=spec["appSlug"], environment=spec["environment"])
    owned_ports = ({item["hostPort"] for item in bindings(current_app)} if current_app else set())
    _assert_bindable([item["hostPort"] for item in bindings(spec)], owned_ports)
    docker = _docker()
    existing = _assert_owned_or_absent(
        docker,
        container_name=spec["containerName"],
        owner_repo=spec["ownerRepo"],
        app_slug=spec["appSlug"],
        environment=spec["environment"],
    )
    evidence_base = {
        "schemaVersion": LOCAL_RUNTIME_SCHEMA_VERSION,
        "ownerRepo": spec["ownerRepo"],
        "appSlug": spec["appSlug"],
        "environment": spec["environment"],
        "containerName": spec["containerName"],
        "image": spec["image"],
        "specSha256": spec["specSha256"],
        "placement": "workstation",
        "exposure": "loopback",
    }
    try:
        if spec.get("imageSource") == "local-image-id":
            _run(docker, ["image", "inspect", spec["image"]])
        else:
            _run(docker, ["pull", spec["image"]])
        # All detectable preflight checks precede removal of the existing container.
        if plan.get("materialSnapshot") != snapshot_material(spec):
            raise DeploymentKitError("External material changed before replacement.")
        _preflight_material(docker, spec)
        if existing is not None:
            _run(docker, ["rm", "-f", spec["containerName"]])
        _run(docker, _container_args(spec))
        _wait_for_health(spec)
    except DeploymentKitError:
        _append_evidence(spec["appSlug"], spec["environment"], {**evidence_base, "outcome": "failed"})
        raise
    # Verify the new container against the approved spec, not persisted state:
    # a late failure must not overwrite the last accepted deployment record.
    try:
        actual = _inspect_owned_container(docker, spec["containerName"])
        if actual is None or not actual["running"]:
            raise DeploymentKitError("Local deployment is not running after health verification.")
        observed = {
            "specSha256": actual["labels"].get(_LABEL_SPEC),
            "actualPorts": actual["ports"],
            "actualHostBindings": actual["hostBindings"],
            "actualMounts": actual["mounts"],
        }
        if actual["labels"].get(_LABEL_OWNER) != spec["ownerRepo"] or (
            actual["labels"].get(_LABEL_APP), actual["labels"].get(_LABEL_ENV)
        ) != (spec["appSlug"], spec["environment"]) or _config_drift(observed, spec):
            raise DeploymentKitError("Local Docker configuration does not match the approved spec.")
        _persist_state(spec)
        final = local_inventory()
        deployed = next(
            (
                item
                for item in final["applications"]
                if item["appSlug"] == spec["appSlug"] and item["environment"] == spec["environment"]
            ),
            None,
        )
        if not deployed or deployed["specSha256"] != spec["specSha256"] or not deployed["httpHealthy"] or deployed.get("configurationDrift", False):
            raise DeploymentKitError("Local deployment completed but readiness evidence is not healthy.")
    except DeploymentKitError:
        _append_evidence(spec["appSlug"], spec["environment"],
                         {**evidence_base, "outcome": "failed", "reason": "post-deploy-verification"})
        raise
    _append_evidence(spec["appSlug"], spec["environment"], {**evidence_base, "outcome": "ready"})
    final["mutated"] = True
    return final


__all__ = [
    "LOCAL_APP_DEPLOY_WRITE_PHRASE",
    "LOOPBACK_ADDRESS",
    "apply_local_deploy",
    "local_deploy_write_phrase",
    "local_inventory",
    "normalize_local_spec",
    "plan_local_deploy",
]
