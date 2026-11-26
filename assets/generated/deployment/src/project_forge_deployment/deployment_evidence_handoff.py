"""Versioned, nonauthorizing Project deployment evidence export (#195).

Uses existing authenticated GitHub publisher-record acquisition and scoped Kit
inventory. Explicit human reports remain attributed claims. A portable export
is not signed and cannot independently authorize an action or prove acceptance.
No dashboard write, publication, deployment, or host mutation.
"""
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .application_publication_status import publication_status, positive_id, DIGEST
from .evidence_records import (
    github_get, COMMIT, read_record, matches, desired_scope, load_inventory, runtime_status,
    timestamp, MAX_INPUT, SLUG,
)
from .release_reconciliation import lifecycle_assessment, observe_registry_manifest, validate_registry_observation
from .errors import DeploymentKitError


# Resolve the trusted Kit import root from this module in Source or an
# installed consumer, never from a record, the working directory or PYTHONPATH.
KIT_SOURCE = Path(__file__).resolve().parents[1]
INVENTORY_RUNNER = (
    "import sys; sys.path.insert(0, sys.argv.pop(1)); "
    "from project_forge_deployment.entrypoint import main; "
    "raise SystemExit(main(sys.argv[1:]))"
)


def collect_inventory(target, *, run=None, clock=None):
    """Bound ordinary read-only inventory in a separate isolated process."""
    run = subprocess.run if run is None else run
    if not isinstance(target, str) or not SLUG.fullmatch(target):
        raise ValueError("explicit target required")
    clock = clock or (lambda: datetime.now(timezone.utc))
    started = clock()
    result = run(
        [sys.executable, "-I", "-B", "-c", INVENTORY_RUNNER,
         str(KIT_SOURCE), "app", "inventory", target, "--json"],
        cwd=KIT_SOURCE, capture_output=True, check=True, timeout=120,
        stdin=subprocess.DEVNULL,
    )
    if not isinstance(result.stdout, bytes) or len(result.stdout) > MAX_INPUT:
        raise ValueError("invalid inventory output")
    # The collection start is a conservative bound, not a host-issued time.
    return result.stdout, started.isoformat()


MAX_REPORT = 32 * 1024
MAX_REPORTS = 100
LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")
ORIGIN = re.compile(r"https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?")
KINDS = {"browser-access", "synthetic-validation", "sqlite-persistence"}
REPORT_FIELDS = {"schemaVersion", "kind", "scope", "sourceCommit", "registryImage",
                 "observation", "result", "observedAt", "reportedBy", "endpoint", "durationSeconds"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact_origin(value):
    if value is None:
        return None
    require(isinstance(value, str) and len(value) <= 270 and ORIGIN.fullmatch(value),
            "explicit HTTP(S) origin only; no path, credentials, query or fragment")
    parsed = urlsplit(value)
    require(parsed.hostname and HOST.fullmatch(parsed.hostname)
            and (parsed.port is None or 1 <= parsed.port <= 65535)
            and ".." not in parsed.hostname, "invalid endpoint origin")
    return value


def bounded_read(path):
    with Path(path).open("rb") as handle:
        data = handle.read(MAX_REPORT + 1)
    require(0 < len(data) <= MAX_REPORT, "bounded observation document required")
    return data


def parse_record(data):
    try:
        return read_record(data)
    except RecursionError:
        raise ValueError("invalid nested observation") from None


def stamp(value):
    require(isinstance(value, datetime) and value.utcoffset() is not None,
            "timezone-aware evaluation time required")
    return value.astimezone(timezone.utc).isoformat()


def freshness(observed, now, max_age):
    age = now - observed
    return "future" if age < timedelta(0) else "stale" if age > max_age else "current"


def field(value=None, *, status="unknown", source=None, observed=None, fresh="unknown"):
    return {"value": value, "status": status, "source": source,
            "observedAt": stamp(observed) if observed is not None else None, "freshness": fresh}


def release_projection(report, scope, run_id, observed):
    """Only called with the existing publisher collector's successful result.

    'verified' here means verified GitHub record/receipt consistency, never
    cryptographic image provenance or verified running state.
    """
    require(isinstance(report, dict)
            and report.get("projectRepository") == scope["ownerRepo"]
            and report.get("appSlug") == scope["appSlug"]
            and report.get("publicationRunId") == run_id
            and report.get("publisherRecord") == "matched"
            and report.get("evidenceAuthority") == "github-run-and-artifact-record-consistency"
            and report.get("authorizesMutation") is False
            and report.get("sourceBuildProvenance") == "not-verified"
            and matches(COMMIT, report.get("sourceCommit"))
            and matches(DIGEST, report.get("recordedLocalImageId"))
            and matches(DIGEST, report.get("archiveDigest"))
            and all(positive_id(report.get(k)) for k in ("publicationAttempt", "projectCiRunId", "artifactId")),
            "inconsistent publisher evidence")
    registry = "ghcr.io/" + scope["ownerRepo"].split("/")[0].lower() + "/" + scope["appSlug"]
    require(matches(re.compile(re.escape(registry) + r"@sha256:[0-9a-f]{64}"), report.get("registryImage")),
            "publisher image scope mismatch")
    source = {"kind": "github-publisher-record-consistency", "repository": scope["ownerRepo"],
              "runId": run_id, "attempt": report["publicationAttempt"], "artifactId": report["artifactId"],
              "archiveDigest": report["archiveDigest"]}
    return {
        "sourceCommit": field(report["sourceCommit"], status="verified", source=source, observed=observed, fresh="historical"),
        "projectCiRunId": field(report["projectCiRunId"], status="verified", source=source, observed=observed, fresh="historical"),
        "publishedImage": field(report["registryImage"], status="verified", source=source, observed=observed, fresh="historical"),
        "publisherRecordedBuiltImageId": field(report["recordedLocalImageId"], status="verified", source=source, observed=observed, fresh="historical"),
    }


def runtime_projection(data, *, scope, observed_at, now, max_age, acquisition, expected_image):
    observed = timestamp(observed_at)
    try:
        report = runtime_status(data, repository=scope["ownerRepo"], app=scope["appSlug"],
                                environment=scope["environment"], target=scope["targetName"],
                                observed_at=observed_at, now=now, max_age=max_age)
    except RecursionError:
        raise ValueError("invalid nested inventory") from None
    fresh = freshness(observed, now, max_age)
    source = {"kind": acquisition, "inventorySha256": report["inventorySha256"]}
    if fresh != "current":
        return {name: field(status="stale" if fresh == "stale" else "unknown",
                            source=source, observed=observed, fresh=fresh)
                for name in ("managedImage", "runtimeHealth", "managedReleaseComparison", "persistenceMode")}
    image = report.get("managedRegistryImage")
    def reported(value):
        return field(value, status="reported" if value is not None and value != "unknown" else "unknown",
                     source=source, observed=observed, fresh=fresh)
    persistence = None
    # Only include persistence mode from the exact validated selected row.
    # Directory mode does not establish SQLite, a mount, or data survival.
    if image is not None:
        inventory = parse_record(data)
        rows = [row for row in inventory["applications"] if
                row.get("ownerRepo") == scope["ownerRepo"] and row.get("appSlug") == scope["appSlug"]
                and row.get("environment") == scope["environment"]]
        require(len(rows) == 1, "ambiguous inventory scope")
        value = rows[0].get("persistenceMode")
        if value is not None:
            require(value in ("none", "directory"), "invalid persistence mode")
        persistence = value
    # A report about a different managed image is not validation of the
    # selected historical publisher release. Keep it as a discrepancy.
    same = image == expected_image if image is not None else False
    return {"managedImage": reported(image),
            "runtimeHealth": reported(report["health"]),
            "managedReleaseComparison": reported(
                "reported-managed-image-differs-from-selected-release" if image is not None and not same
                else report["managedReleaseComparison"]),
            "persistenceMode": reported(persistence)}


def human_report(data, *, scope, commit, image, endpoint, now, max_age):
    require(isinstance(data, bytes) and 0 < len(data) <= MAX_REPORT, "bounded human report required")
    row = parse_record(data)
    require(set(row) == REPORT_FIELDS and type(row.get("schemaVersion")) is int
            and row["schemaVersion"] == 1 and row.get("kind") == "deployment-observation"
            and row.get("scope") == scope and row.get("sourceCommit") == commit
            and row.get("registryImage") == image and row.get("observation") in KINDS
            and row.get("result") in ("passed", "failed")
            and matches(LOGIN, row.get("reportedBy")), "invalid or differently scoped human report")
    observed = timestamp(row["observedAt"])
    fresh = freshness(observed, now, max_age)
    require(fresh != "future", "human report cannot be from the future")
    origin = exact_origin(row["endpoint"])
    require(origin == endpoint, "human report endpoint differs from selected origin")
    if row["observation"] == "browser-access":
        require(origin is not None, "browser report requires explicit endpoint origin")
    duration = row["durationSeconds"]
    require(duration is None or (type(duration) is int and 0 <= duration <= 86400),
            "invalid observation duration")
    if row["observation"] == "synthetic-validation":
        require(duration is not None, "synthetic validation duration required")
    return {"observation": row["observation"], "result": row["result"],
            "reportedBy": row["reportedBy"], "endpoint": origin, "durationSeconds": duration,
            "source": {"kind": "explicit-human-report", "sha256": hashlib.sha256(data).hexdigest()},
            "observedAt": stamp(observed), "status": "reported", "freshness": fresh,
            "reporterAuthenticity": "not-verified"}


def human_projection(documents, *, scope, commit, image, endpoint, now, max_age):
    require(len(documents) <= MAX_REPORTS, "too many human reports")
    history = [human_report(data, scope=scope, commit=commit, image=image, endpoint=endpoint,
                            now=now, max_age=max_age) for data in documents]
    require(len({row["source"]["sha256"] for row in history}) == len(history), "duplicate human report")
    history.sort(key=lambda row: (timestamp(row["observedAt"]), row["source"]["sha256"]))
    current = {}
    for kind in sorted(KINDS):
        rows = [row for row in history if row["observation"] == kind]
        if not rows:
            current[kind] = field()
            continue
        last = rows[-1]
        observed = timestamp(last["observedAt"])
        latest = [row for row in rows if timestamp(row["observedAt"]) == observed]
        # No arbitrary winner for simultaneous contradictory reports.
        if len({row["result"] for row in latest}) > 1:
            current[kind] = field(status="unknown", source={"kind": "conflicting-human-reports",
                "sha256s": sorted(row["source"]["sha256"] for row in latest)}, observed=observed,
                fresh=last["freshness"])
            continue
        source = {"kind": "explicit-human-reports", "sha256s": sorted(row["source"]["sha256"] for row in latest)}
        current[kind] = field(last["result"] if last["freshness"] == "current" else None,
                              status="reported" if last["freshness"] == "current" else "stale",
                              source=source, observed=observed, fresh=last["freshness"])
    return history, current


def pr_fallback(repository, number, head, base, *, get=github_get):
    """Authenticated exact-PR/compare metadata, no private diff content export."""
    require(positive_id(number) and matches(COMMIT, head) and matches(COMMIT, base) and head != base,
            "explicit PR number and exact head/base required")
    endpoint = f"repos/{repository}/pulls/{number}"
    pr = get(endpoint)
    require(isinstance(pr, dict) and pr.get("number") == number
            and pr.get("head", {}).get("sha") == head and pr.get("base", {}).get("sha") == base
            and pr.get("head", {}).get("repo", {}).get("full_name") == repository
            and pr.get("base", {}).get("repo", {}).get("full_name") == repository
            and pr.get("merged") is True and matches(COMMIT, pr.get("merge_commit_sha")),
            "PR exact head/base or repository changed")
    comparison = get(f"repos/{repository}/compare/{base}...{head}")
    files = comparison.get("files")
    # GitHub compare file lists are capped at 300. Never present a capped or
    # mismatched list as a complete diff. No actual patch bytes are exported.
    require(comparison.get("merge_base_commit", {}).get("sha") == base
            and comparison.get("base_commit", {}).get("sha") == base
            and type(pr.get("changed_files")) is int
            and isinstance(files, list) and 0 < len(files) == pr["changed_files"] < 300
            and all(isinstance(row, dict) and isinstance(row.get("filename"), str)
                    and isinstance(row.get("status"), str) for row in files)
            and len({row["filename"] for row in files}) == len(files),
            "complete same-base changed-file comparison unavailable")
    require(get(endpoint) == pr, "PR changed during acquisition")
    # Export an identity for the complete changed-file metadata, not a patch
    # checksum or an assertion that independent review has been performed.
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"number": number, "head": head, "base": base, "mergeCommit": pr["merge_commit_sha"],
            "changedFileCount": len(files),
            "changedFileMetadataSha256": digest, "patchReview": "not-performed",
            "source": "authenticated-github-pr-and-exact-compare"}


def build_handoff(repository, *, app, environment, target, publication_run, endpoint=None,
                  inventory=None, inventory_path=None, observed_at=None, collect=False, documents=(),
                  pr=None, now=None, runtime_max_age=timedelta(minutes=5),
                  human_max_age=timedelta(days=7), publisher=publication_status,
                  inventory_collector=collect_inventory, pr_inspector=pr_fallback, partial=False,
                  collect_registry=False, registry_inspector=observe_registry_manifest, clock=None):
    scope = desired_scope(repository, app, environment, target)
    supplied = inventory is not None or inventory_path is not None
    require(positive_id(publication_run)
            and sum((bool(collect), inventory is not None, inventory_path is not None)) <= 1
            and supplied == (observed_at is not None),
            "explicit publication run and one optional inventory mode required")
    if supplied:
        timestamp(observed_at)
    endpoint = exact_origin(endpoint)
    if pr is not None:
        require(isinstance(pr, tuple) and len(pr) == 3 and positive_id(pr[0])
                and matches(COMMIT, pr[1]) and matches(COMMIT, pr[2]) and pr[1] != pr[2],
                "explicit PR number and exact head/base required")
    require(len(documents) <= MAX_REPORTS, "too many human reports")
    require(all(isinstance(x, timedelta) and x > timedelta(0)
                for x in (runtime_max_age, human_max_age)), "positive freshness limits required")
    clock = (lambda: now) if now is not None else (clock or (lambda: datetime.now(timezone.utc)))
    started = clock()
    stamp(started)
    published = publisher(repository, publication_run)
    release = release_projection(published, scope, publication_run, started)
    commit, image = release["sourceCommit"]["value"], release["publishedImage"]["value"]
    errors = (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError,
              AttributeError, OverflowError, RecursionError, DeploymentKitError)
    stages = {"publication": "collected", "pullRequest": "not-requested", "runtime": "not-requested"}
    registry = None
    if collect_registry:
        try:
            registry = validate_registry_observation(registry_inspector(published), published)
            stages["registry"] = "collected"
        except errors:
            if not partial:
                raise
            stages["registry"] = "unavailable"
    release["pullRequestIdentity"] = field()
    if pr is not None:
        try:
            pr_record = pr_inspector(repository, *pr)
            require(pr_record.get("number") == pr[0] and pr_record.get("head") == pr[1]
                    and pr_record.get("base") == pr[2] and pr_record.get("mergeCommit") == commit
                    and pr_record.get("patchReview") == "not-performed",
                    "PR merge commit does not match selected publication source")
            release["pullRequestIdentity"] = field(pr_record, status="verified",
                source={"kind": "authenticated-github-pr-and-exact-compare"}, observed=clock(), fresh="historical")
            stages["pullRequest"] = "collected"
        except errors:
            if not partial:
                raise
            stages["pullRequest"] = "unavailable"
    runtime = {name: field() for name in
               ("managedImage", "runtimeHealth", "managedReleaseComparison", "persistenceMode")}
    if collect or supplied:
        try:
            if collect:
                inventory, observed_at = inventory_collector(target)
            elif inventory_path is not None:
                inventory = load_inventory(inventory_path)
            evaluated = clock()
            runtime = runtime_projection(inventory, scope=scope, observed_at=observed_at, now=evaluated,
                max_age=runtime_max_age, acquisition="local-kit-inventory" if collect else "supplied-kit-inventory",
                expected_image=image)
            stages["runtime"] = "collected"
        except errors:
            if not partial:
                raise
            stages["runtime"] = "unavailable"
    evaluated = clock()
    stamp(evaluated)
    history, human = human_projection(documents, scope=scope, commit=commit, image=image,
                                      endpoint=endpoint, now=evaluated, max_age=human_max_age)
    # Reuse the same advisory assessment as project_alignment_status. The
    # handoff's independently scoped, sanitized runtime projection remains
    # reported evidence; a stale/unknown field cannot establish a match.
    managed = runtime["managedImage"]
    lifecycle_runtime = {"scope": scope, "managedRegistryImage": managed["value"],
                         "observedAtReported": managed["observedAt"],
                         "freshness": {"current": "within-reported-window",
                                       "stale": "stale-reported", "future": "future-reported"}.get(managed["freshness"]),
                         "managedReleaseComparison": runtime["managedReleaseComparison"]["value"],
                         "health": runtime["runtimeHealth"]["value"]}
    result = {"schemaVersion": 1, "kind": "project-forge-deployment-evidence-handoff",
            "scope": scope, "evaluatedAt": stamp(evaluated), "release": release, "runtime": runtime,
            "accessEndpoint": field(endpoint, status="reported" if endpoint else "unknown",
                source={"kind": "explicit-operator-selection"} if endpoint else None,
                observed=started if endpoint else None, fresh="not-verified" if endpoint else "unknown"),
            "humanObservations": history, "currentHumanObservations": human,
            "actualRuntimeImageId": field(), "approvedDesiredRelease": field(),
            "sourceBuildProvenance": field(), "formalAcceptance": field(),
            "compatibility": field(), "dashboard": {"state": "not-recorded", "importAuthorized": False},
            "diagnostics": {"collectionState": "incomplete" if "unavailable" in stages.values() else "collected",
                            "stages": stages},
            "authorizesMutation": False}
    result["lifecycleReadiness"] = lifecycle_assessment(
        publication=published, registry=registry, runtime=lifecycle_runtime, now=evaluated,
        runtime_max_age=runtime_max_age)
    if collect_registry:
        result["applicationRegistryStatus"] = registry
    return result


def write_export(bundle, output):
    """Explicit local exclusive-create only; no Project/dashboard mutation."""
    text = json.dumps(bundle, indent=2, sort_keys=True) + "\n"
    if output is not None:
        with Path(output).open("x", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text, end="")


