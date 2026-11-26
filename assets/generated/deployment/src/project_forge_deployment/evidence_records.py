"""Portable strict read-only evidence records and GitHub transport.

Existing authenticated gh context only; no private platform checkout required.
Reports are diagnostic and confer no authorization.
"""
import base64
import binascii
import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone

COMMIT = re.compile(r"[0-9a-f]{40}")
REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
IMAGE = re.compile(r"[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}")
SPEC = re.compile(r"[0-9a-f]{64}")
MAX_RECORD_BYTES = 1024 * 1024
MAX_INPUT = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("nonstandard JSON constant")


def read_record(data):
    if not isinstance(data, bytes):
        raise ValueError("exact document bytes required")
    result = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object,
                        parse_constant=reject_constant)
    if not isinstance(result, dict):
        raise ValueError("object required")
    return result


def matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def repository_name(value):
    if (not isinstance(value, str) or not REPOSITORY.fullmatch(value)
            or value.split("/")[1] in {".", ".."}):
        raise ValueError("expected owner/repository on github.com")
    return value


def github_get(endpoint):
    """One bounded GET via existing gh authentication; never echo stderr."""
    result = subprocess.run(
        ["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint],
        capture_output=True, timeout=30, check=True, stdin=subprocess.DEVNULL,
    )
    if not isinstance(result.stdout, bytes) or not 0 < len(result.stdout) <= MAX_RESPONSE_BYTES:
        raise ValueError("bounded GitHub response required")
    return read_record(result.stdout)


def read_blob(repository, commit, path, get):
    result = get(f"repos/{repository}/contents/{path}?ref={commit}")
    if (result.get("type") != "file" or result.get("path") != path
            or result.get("encoding") != "base64"
            or not isinstance(result.get("content"), str)
            or type(result.get("size")) is not int
            or not 0 <= result["size"] <= MAX_RECORD_BYTES
            or len(result["content"]) > 2 * MAX_RECORD_BYTES):
        raise ValueError("unsupported GitHub content response")
    try:
        data = base64.b64decode(result["content"].replace("\n", ""), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("invalid encoded content") from exc
    if len(data) != result["size"]:
        raise ValueError("content size mismatch")
    git_blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
    if git_blob != result.get("sha"):
        raise ValueError("Git blob identity mismatch")
    return data, git_blob


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone required")
    return result.astimezone(timezone.utc)


def desired_scope(repository, app, environment, target):
    repository_name(repository)
    if not all(isinstance(x, str) and SLUG.fullmatch(x) for x in (app, environment, target)):
        raise ValueError("explicit desired release scope required")
    return {"ownerRepo": repository, "appSlug": app,
            "environment": environment, "targetName": target}


def runtime_status(data, *, repository, app, environment, target, observed_at, now, max_age):
    repository_name(repository)
    if not all(isinstance(x, str) and SLUG.fullmatch(x) for x in (app, environment, target)):
        raise ValueError("explicit runtime scope required")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("timezone-aware evaluation time required")
    if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
        raise ValueError("positive freshness limit required")
    result = {
        "evidenceAuthority": "caller-supplied-unverified",
        "comparisonOnly": True, "authorizesMutation": False,
        "scope": {"ownerRepo": repository, "appSlug": app,
                  "environment": environment, "targetName": target},
        "inventorySha256": hashlib.sha256(data).hexdigest(),
        "observedAtReported": timestamp(observed_at).isoformat(),
        "evaluatedAt": now.isoformat(),
        "managedReleaseComparison": "unknown",
        "health": "unknown", "approvedDesiredAlignment": "not-evaluated",
        "sourceBuildProvenance": "not-evaluated",
        "recommendedAction": "refresh-runtime-evidence",
    }
    inventory = read_record(data)
    if inventory.get("mutated") is not False or inventory.get("targetName") != target:
        raise ValueError("inventory target or read-only marker mismatch")
    apps = inventory.get("applications")
    if not isinstance(apps, list) or any(not isinstance(row, dict) for row in apps):
        raise ValueError("invalid application inventory")
    rows = [row for row in apps if row.get("appSlug") == app and row.get("environment") == environment]
    if len(rows) > 1 or any(row.get("ownerRepo") != repository for row in rows):
        raise ValueError("duplicate or conflicting application ownership")
    age = now - timestamp(observed_at)
    if age < timedelta(0) or age > max_age:
        result["freshness"] = "future-reported" if age < timedelta(0) else "stale-reported"
        return result
    result["freshness"] = "within-reported-window"
    if not rows:
        result["managedReleaseComparison"] = "reported-not-listed"
        result["recommendedAction"] = "verify-application-inventory"
        return result
    row = rows[0]
    image, spec = row.get("image"), row.get("specSha256")
    if not isinstance(image, str) or not IMAGE.fullmatch(image) or not isinstance(spec, str) or not SPEC.fullmatch(spec):
        raise ValueError("invalid managed image or spec identity")
    flags = ("containerPresent", "imageMatchesRelease", "containerRunning",
             "connectedToSharedNetwork", "httpHealthy")
    if any(type(row.get(flag)) is not bool for flag in flags):
        return result
    present, matches, running, network, healthy = (row[flag] for flag in flags)
    if (not present and any((matches, running, network, healthy))) or (
            healthy and not all((present, matches, running, network))):
        raise ValueError("contradictory runtime evidence")
    result["managedRegistryImage"] = image
    result["managedSpecSha256"] = spec
    if not present:
        result["managedReleaseComparison"] = "reported-container-absent"
    elif matches:
        result["managedReleaseComparison"] = "reported-match"
    else:
        result["managedReleaseComparison"] = "reported-mismatch"
    result["health"] = "reported-healthy" if healthy else "reported-not-healthy"
    result["recommendedAction"] = (
        "verify-managed-release-and-approved-desired-state" if matches and healthy
        else "investigate-reported-runtime-state")
    return result


def load_inventory(path):
    with open(path, "rb") as handle:
        data = handle.read(MAX_INPUT + 1)
    if len(data) > MAX_INPUT:
        raise ValueError("inventory exceeds size limit")
    return data


