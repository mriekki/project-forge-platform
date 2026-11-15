#!/usr/bin/env python3
"""Qualify an unpublished Auth-enabled Project Forge package in a disposable Project.

Uses the actual assembled npm package, exact Auth Kit managed runtime, and
Git-blob-pinned Bootstrap fixture carried by the reviewed Auth Kit source.
No publication, provider calls, credentials, Production, host, or Docker changes.
This is package/generation acceptance, NOT full application recovery readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def _run(args: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 240,
         expected_success: bool = True) -> subprocess.CompletedProcess[str]:
    outcome = subprocess.run(
        args, cwd=cwd, env=env, capture_output=True, text=True,
        timeout=timeout, check=False,
    )
    if (outcome.returncode == 0) != expected_success:
        # All inputs are synthetic, but never dump environment or subprocess
        # output, which could contain unrelated Actions runner values.
        raise RuntimeError("Disposable Auth candidate command failed the expected outcome: "
                           + args[0] + " " + (args[1] if len(args) > 1 else ""))
    return outcome


def _bootstrap_module(source: Path):
    """Reuse the Auth Kit's independently Git-blob-pinned Bootstrap snapshot."""
    tests = source / "tests"
    entry = tests / "test_project_auth_bootstrap_integration.py"
    if not entry.is_file() or entry.is_symlink():
        raise RuntimeError("Exact Auth Kit Bootstrap integration contract is missing.")
    sys.path.insert(0, str(tests))
    try:
        spec = importlib.util.spec_from_file_location("candidate_bootstrap_contract", entry)
        if spec is None or spec.loader is None:
            raise RuntimeError("Auth Kit Bootstrap module cannot be loaded.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        bootstrap = module.bootstrap_module()  # verifies the pinned Git blob
        return bootstrap, module.request(), module.BOOTSTRAP_SHA
    finally:
        sys.path.remove(str(tests))


def _isolated_environment(home: Path) -> dict[str, str]:
    # Never pass runner/provider credentials into npm or the generated API
    # build. The local package and synthetic generated Project need no tokens.
    result = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "CI": "true",
        "NPM_CONFIG_AUDIT": "false",
        "NPM_CONFIG_FUND": "false",
        "NPM_CONFIG_USERCONFIG": str(home / ".npmrc"),
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        "DOTNET_NOLOGO": "1",
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
    }
    for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG",
                "DOTNET_ROOT", "DOTNET_ROOT_X64"):
        if key in os.environ:
            result[key] = os.environ[key]
    (home / ".npmrc").write_text("", encoding="utf-8")
    return result


def _prove_package_runtime_recovery(
    consumer: Path, auth_source: Path, work: Path, env: dict[str, str]
) -> dict:
    """Qualify actual packaged Auth Runtime and recovery helper, not repo src.

    The fixture itself is read from the exact protected Auth Kit source
    checkout; the executable it compiles references only the npm-installed
    generated Project Runtime. No provider, Docker host or Production access.
    """
    proof_source = auth_source / "tests/generated_project_recovery_proof.py"
    if not proof_source.is_file() or proof_source.is_symlink():
        raise RuntimeError(
            "Accepted Authentication source has no generated-Project recovery proof.")
    spec = importlib.util.spec_from_file_location(
        "exact_generated_auth_recovery_proof", proof_source)
    if spec is None or spec.loader is None:
        raise RuntimeError("Exact Auth recovery proof could not be loaded.")
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    evidence = harness.prove_generated_project_auth_recovery(
        consumer, work, auth_source=auth_source, env=env)
    success = (
        "installedRuntimeUsed",
        "installedRecoveryHelperUsed",
        "sqliteAndKeyRingCaptured",
        "isolatedRestoreVerified",
        "protectorAndSessionContinuityProven",
        "restoredHttpAndCsrfProven",
        "originalLiveSessionUntouched",
        "tamperedKeyRingRejected",
    )
    not_ready = (
        "applicationRecoveryReady",
        "dockerQuiescenceVerified",
        "providerAcceptanceVerified",
        "scheduledBackupVerified",
        "alertInboxReceiptVerified",
    )
    if (type(evidence) is not dict or
            any(evidence.get(name) is not True for name in success) or
            any(evidence.get(name) is not False for name in not_ready)):
        raise RuntimeError(
            "Generated Project Auth runtime recovery evidence is incomplete or overstated.")
    return evidence


def qualify(package_root: Path, auth_source: Path) -> dict:
    package_root = package_root.resolve(strict=True)
    auth_source = auth_source.resolve(strict=True)
    if not (auth_source / "distributions/greenfield-project.json").is_file():
        raise RuntimeError("Reviewed Auth Kit source distribution is unavailable.")
    package_json = json.loads((package_root / "package.json").read_text("utf-8"))
    if package_json.get("name") != "@mriekki/project-forge":
        raise RuntimeError("Unexpected package under qualification.")
    with tempfile.TemporaryDirectory(prefix="pf-auth-candidate-") as dirname:
        root = Path(dirname)
        home = root / "private-home"
        home.mkdir(mode=0o700)
        env = _isolated_environment(home)
        packed = root / "packed"
        packed.mkdir()
        result = _run([
            "npm", "pack", str(package_root), "--ignore-scripts", "--json",
            "--pack-destination", str(packed)], cwd=root, env=env)
        manifests = json.loads(result.stdout)
        if type(manifests) is not list or len(manifests) != 1:
            raise RuntimeError("Expected exactly one unpublished npm candidate.")
        archive = packed / manifests[0]["filename"]
        if not archive.is_file():
            raise RuntimeError("Unpublished candidate tarball missing.")
        candidate_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()

        install_root = root / "installed"
        install_root.mkdir()
        (install_root / "package.json").write_text('{"private":true}\n', encoding="utf-8")
        _run([
            "npm", "install", "--ignore-scripts", "--no-audit", "--no-fund",
            str(archive)], cwd=install_root, env=env)
        pkg = install_root / "node_modules/@mriekki/project-forge"
        installed_assets = json.loads((pkg / "assets/components.json").read_text("utf-8"))
        if installed_assets.get("version") != package_json.get("version"):
            raise RuntimeError("Installed candidate version mismatch.")
        profiles = installed_assets["profiles"]
        if "authentication" in profiles["greenfield-project"]["components"]:
            raise RuntimeError("Standard Project profile unexpectedly enables Auth.")
        if profiles["greenfield-household-project"]["components"] != [
                "core", "deployment", "authentication"]:
            raise RuntimeError("Auth candidate profile does not declare exact components.")

        bootstrap, request, bootstrap_sha = _bootstrap_module(auth_source)
        approved = bootstrap.validate_request({
            "stack": {"recipe": "dotnet-react-sqlite"},
            "generation": {"householdAuth": request},
        })
        bootstrap.require_packaged_auth(
            pkg, installed_assets, profiles["greenfield-household-project"], approved)

        consumer = root / "consumer"
        consumer.mkdir()
        cli = ["node", str(pkg / "bin/project-forge.mjs")]
        options = ["--root", str(consumer), "--profile", "greenfield-household-project"]
        _run(cli + ["install"] + options + [
            "--apply", "--consumer", "auth-candidate-disposable",
            "--consumer-baseline", "synthetic-qualification-only",
        ], cwd=root, env=env)
        _run(cli + ["check"] + options, cwd=root, env=env)
        baselines = ("CORE_BASELINE.json", "DEPLOYMENT_BASELINE.json",
                     "AUTHENTICATION_BASELINE.json", "PROJECT_FORGE_BASELINE.json")
        for name in baselines:
            if not (consumer / name).is_file():
                raise RuntimeError("Candidate omitted an exact component baseline.")
        auth_baseline = json.loads(
            (consumer / "AUTHENTICATION_BASELINE.json").read_text("utf-8"))
        if auth_baseline.get("revision") != installed_assets["components"]["authentication"]["revision"]:
            raise RuntimeError("Generated Auth baseline differs from candidate.")

        managed = consumer / "tools/project-forge-auth-kit/project_auth_recovery.py"
        packaged = pkg / "assets/generated/authentication/tools/project_auth_recovery.py"
        if not managed.is_file() or managed.read_bytes() != packaged.read_bytes():
            raise RuntimeError("Generated Project Auth recovery source differs from candidate.")
        baseline_copy = {
            name: (consumer / name).read_bytes() for name in baselines
        }
        managed.unlink()
        _run(cli + ["check"] + options, cwd=root, env=env, expected_success=False)
        _run(cli + ["repair"] + options + ["--apply"], cwd=root, env=env)
        _run(cli + ["check"] + options, cwd=root, env=env)
        if managed.read_bytes() != packaged.read_bytes() or any(
            (consumer / name).read_bytes() != before
            for name, before in baseline_copy.items()
        ):
            raise RuntimeError("Candidate repair changed accepted managed provenance.")

        bootstrap.materialize_reference_project(consumer, approved)
        intent_path = bootstrap.write_setup_intent(consumer, {
            "generation": {"project-forge": {
                "version": package_json["version"],
                "profile": "greenfield-household-project",
            }}
        }, approved)
        intent = json.loads(intent_path.read_text("utf-8"))
        if (intent.get("productionActivationAuthorized") is not False or
                intent.get("applicationCredentialsStored") is not False or
                intent.get("automaticHouseholdMembership") is not False):
            raise RuntimeError("Candidate activated an unapproved household provider.")
        api = consumer / "src/ProjectForgeAuth.Api/ProjectForgeAuth.Api.csproj"
        _run(["dotnet", "build", str(api), "--configuration", "Release",
              "--nologo", "-v", "minimal"], cwd=consumer, env=env, timeout=300)
        _run(cli + ["check"] + options, cwd=root, env=env)

        recovery_work = root / "generated-runtime-recovery"
        recovery_work.mkdir(mode=0o700)
        recovery = _prove_package_runtime_recovery(
            consumer, auth_source, recovery_work, env)

        return {
            "result": "disposable-candidate-generation-build-and-recovery-passed",
            "generatedRuntimeRecoveryProven": recovery["isolatedRestoreVerified"],
            "generatedRuntimeHttpSessionAndCsrfProven": recovery["restoredHttpAndCsrfProven"],
            "version": package_json["version"],
            "archiveSha256": candidate_sha256,
            "bootstrapRevision": bootstrap_sha,
            "realAuthSource": True,
            "realDeploymentSource": True,
            "applicationRecoveryReady": False,
            "providerAcceptanceVerified": False,
            "npmPublished": False,
            "productionModified": False,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--authentication-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(qualify(args.package_root, args.authentication_root),
                         sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        print("BLOCKED: unpublished Auth candidate generation qualification failed.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
