"""Explicit, reusable workstation SSH-agent session for Deployment Kit commands.

This owns *local* authentication only. It does not authorize any remote write,
alter target host trust, start an SSH tunnel, or change an operating-system service.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
from typing import Iterator

from .errors import DeploymentKitError
from .keys import add_key_to_agent, agent_status
from .security import check_identity_security


def _private_agent_directory(profile: dict[str, str]) -> Path:
    identity = Path(profile["identityFile"])
    check_identity_security(identity)
    ssh_dir = next((p for p in identity.parents if p.name.lower() == ".ssh"), None)
    if ssh_dir is None:
        raise DeploymentKitError("The configured identity is outside the user's .ssh directory.")
    directory = ssh_dir / "project-forge-agents"
    if not directory.exists() and not directory.is_symlink():
        directory.mkdir(mode=0o700)
    try:
        metadata = directory.lstat()
    except OSError as error:
        raise DeploymentKitError("Cannot inspect the dedicated SSH-agent directory.") from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_mode & 0o077
    ):
        raise DeploymentKitError(
            "Dedicated SSH-agent directory must be a real, current-user-owned directory with mode 0700."
        )
    return directory


def _agent_socket(profile: dict[str, str]) -> Path:
    directory = _private_agent_directory(profile)
    digest = hashlib.sha256(
        str(Path(profile["identityFile"]).resolve()).encode("utf-8")
    ).hexdigest()[:16]
    socket = directory / f"pf-{digest}.sock"
    # Some OSes limit Unix-domain socket paths to ~104 bytes.
    if len(os.fsencode(socket)) > 100:
        raise DeploymentKitError(
            "The dedicated SSH-agent socket path is too long for portable Unix socket support."
        )
    return socket


def _ensure_posix_agent_socket(profile: dict[str, str]) -> str:
    socket = _agent_socket(profile)
    if socket.is_symlink():
        raise DeploymentKitError("Refusing to follow a symlink at the dedicated SSH-agent socket.")
    if socket.exists():
        metadata = socket.lstat()
        if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise DeploymentKitError("Dedicated SSH-agent socket is not a current-user-owned Unix socket.")
    else:
        agent = shutil.which("ssh-agent")
        if not agent:
            raise DeploymentKitError("OpenSSH ssh-agent is not installed on this workstation.")
        result = subprocess.run(
            [agent, "-a", str(socket), "-s"],
            check=False, text=True, capture_output=True,
        )
        if result.returncode or not socket.is_socket():
            raise DeploymentKitError(
                "Cannot start the dedicated SSH agent. Inspect the private socket directory; "
                "no existing agent process or socket will be removed automatically."
            )

    # Do not trust an old socket solely because it looks like a socket: it must
    # respond to the usual identity check under the exact selected environment.
    return str(socket)


def _set_socket(value: str | None) -> None:
    if value is None:
        os.environ.pop("SSH_AUTH_SOCK", None)
    else:
        os.environ["SSH_AUTH_SOCK"] = value


@contextmanager
def target_agent_session(profile: dict[str, str]) -> Iterator[dict[str, str | bool]]:
    """Temporarily bind the selected target's agent to commands in this process.

    WSL/Linux: a stable per-identity local OpenSSH agent survives separate
    VS Code terminal processes. macOS: prefer its existing launchd agent when
    available, otherwise use the same private stable POSIX fallback.
    Native Windows: use the existing Windows OpenSSH agent *service* only.
    Its service setup/start requires a separately authorized workstation action.
    """
    system = platform.system()
    previous = os.environ.get("SSH_AUTH_SOCK")
    managed_socket = False
    try:
        if system == "Windows":
            # A native Windows OpenSSH service does not use SSH_AUTH_SOCK.
            # Never start or reconfigure the privileged service automatically.
            _set_socket(None)
        elif system in {"Linux", "Darwin"}:
            if system == "Darwin" and previous:
                status = agent_status(profile)
                if status["state"] == "agent-unavailable":
                    _set_socket(_ensure_posix_agent_socket(profile))
                    managed_socket = True
            else:
                _set_socket(_ensure_posix_agent_socket(profile))
                managed_socket = True
        else:
            raise DeploymentKitError(
                f"Unsupported workstation OS for SSH-agent session: {system}."
            )

        status = agent_status(profile)
        if status["state"] == "agent-unavailable":
            if system == "Windows":
                raise DeploymentKitError(
                    "Windows OpenSSH ssh-agent service is unavailable. "
                    "Have the workstation administrator enable/start the ssh-agent service; "
                    "Project Forge will not change its configuration automatically."
                )
            raise DeploymentKitError(
                "The selected SSH-agent socket is unresponsive. "
                "Inspect the private socket and agent process; Project Forge will not delete it automatically."
            )

        # The explicit 'agent-session' command authorizes this bounded local
        # key load. SSH passphrase input remains with OpenSSH in the terminal.
        if not status["loaded"]:
            result = add_key_to_agent(profile)
            if not result["loaded"]:
                raise DeploymentKitError("Dedicated SSH identity is not loaded.")
        yield {
            "targetName": profile["targetName"],
            "loaded": True,
            "agent": "windows-service" if system == "Windows"
                     else "dedicated-socket" if managed_socket
                     else "existing-macos-agent",
        }
    finally:
        _set_socket(previous)
