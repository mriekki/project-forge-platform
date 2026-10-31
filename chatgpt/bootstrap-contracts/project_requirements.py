from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

STATES = {"draft", "review", "approved"}
TARGETS = {"V1", "V2", "V3"}
TARGET_DISPOSITIONS = {"committed", "planned", "directional"}
TREATMENTS = {"preserve", "reconcile", "reference", "exclude"}
REPOSITORY_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(errors: list[str], value: Any, path: str) -> None:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return
    for index, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{path}[{index}] must be a string")


def validate_project_requirements(document: Any, *, require_approved: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["document must be an object"]

    if document.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1")

    state = document.get("state")
    if state not in STATES:
        errors.append(f"state must be one of {sorted(STATES)}")
    elif require_approved and state != "approved":
        errors.append("state must be approved for replatform use")

    source = document.get("source")
    if not isinstance(source, dict):
        errors.append("source must be an object")
    else:
        repository = source.get("repository")
        if not _non_empty(repository) or not REPOSITORY_RE.fullmatch(repository):
            errors.append("source.repository must be owner/name")
        commit = source.get("commit")
        if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
            errors.append("source.commit must be a full lowercase 40-character Git commit SHA")
        if "exportedAt" in source and not _non_empty(source["exportedAt"]):
            errors.append("source.exportedAt must be a non-empty string")

    project = document.get("project")
    if not isinstance(project, dict):
        errors.append("project must be an object")
    else:
        if not _non_empty(project.get("name")):
            errors.append("project.name is required")
        if not _non_empty(project.get("description")):
            errors.append("project.description is required")
        if "slug" in project and (not _non_empty(project["slug"]) or not SLUG_RE.fullmatch(project["slug"])):
            errors.append("project.slug must match ^[a-z0-9][a-z0-9-]*$")

    product = document.get("product")
    if not isinstance(product, dict):
        errors.append("product must be an object")
    else:
        for key in ("sourcePath", "goal"):
            if not _non_empty(product.get(key)):
                errors.append(f"product.{key} is required")
        for key in (
            "users",
            "outcomes",
            "scope",
            "nonGoals",
            "workflows",
            "successCriteria",
            "openDecisions",
        ):
            if key in product:
                _string_list(errors, product[key], f"product.{key}")
        for required_list in ("users", "nonGoals", "successCriteria"):
            if required_list not in product:
                errors.append(f"product.{required_list} is required")

    features = document.get("features")
    if not isinstance(features, list):
        errors.append("features must be an array")
    else:
        seen_ids: set[str] = set()
        for index, item in enumerate(features):
            path = f"features[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{path} must be an object")
                continue
            for key in ("sourceId", "title", "sourcePath", "status", "summary"):
                if not _non_empty(item.get(key)):
                    errors.append(f"{path}.{key} is required")
            source_id = item.get("sourceId")
            if isinstance(source_id, str):
                if source_id in seen_ids:
                    errors.append(f"{path}.sourceId duplicates {source_id!r}")
                seen_ids.add(source_id)
            target = item.get("target")
            disposition = item.get("targetDisposition")
            if target not in TARGETS:
                errors.append(f"{path}.target must be one of {sorted(TARGETS)}")
            if disposition not in TARGET_DISPOSITIONS:
                errors.append(f"{path}.targetDisposition must be one of {sorted(TARGET_DISPOSITIONS)}")
            if target == "V1" and disposition != "committed":
                errors.append(f"{path}.targetDisposition must be committed for V1")
            if target == "V2" and disposition != "planned":
                errors.append(f"{path}.targetDisposition must be planned for V2")
            if target == "V3" and disposition != "directional":
                errors.append(f"{path}.targetDisposition must be directional for V3")
            for key in (
                "userOutcomes",
                "scope",
                "nonScope",
                "workflows",
                "businessRules",
                "acceptanceCriteria",
                "dependencies",
                "learningObjectives",
                "openQuestions",
            ):
                if key in item:
                    _string_list(errors, item[key], f"{path}.{key}")

    roadmap = document.get("roadmap")
    if not isinstance(roadmap, dict):
        errors.append("roadmap must be an object")
    else:
        milestones = roadmap.get("milestones")
        if not isinstance(milestones, list):
            errors.append("roadmap.milestones must be an array")
        if "sequencingNotes" in roadmap:
            _string_list(errors, roadmap["sequencingNotes"], "roadmap.sequencingNotes")

    for object_field in ("domain", "experience", "crossCuttingRequirements", "learningIntent"):
        if object_field in document and not isinstance(document[object_field], dict):
            errors.append(f"{object_field} must be an object")

    if "decisions" in document and not isinstance(document["decisions"], list):
        errors.append("decisions must be an array")

    artifacts = document.get("sourceArtifacts")
    if not isinstance(artifacts, list):
        errors.append("sourceArtifacts must be an array")
    else:
        for index, item in enumerate(artifacts):
            path = f"sourceArtifacts[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{path} must be an object")
                continue
            for key in ("path", "kind", "authority"):
                if not _non_empty(item.get(key)):
                    errors.append(f"{path}.{key} is required")
            if item.get("treatment") not in TREATMENTS:
                errors.append(f"{path}.treatment must be one of {sorted(TREATMENTS)}")
            if "reason" in item and not isinstance(item["reason"], str):
                errors.append(f"{path}.reason must be a string")

    return errors


def read_document(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("project requirements document must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate canonical PROJECT_REQUIREMENTS.json")
    parser.add_argument("path", nargs="?", default="PROJECT_REQUIREMENTS.json")
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()

    path = Path(args.path)
    try:
        document = read_document(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"INVALID PROJECT_REQUIREMENTS.json: {exc}")
        return 1

    errors = validate_project_requirements(document, require_approved=args.require_approved)
    if errors:
        print("INVALID PROJECT_REQUIREMENTS.json")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"VALID PROJECT_REQUIREMENTS.json state={document['state']} source={document['source']['repository']}@{document['source']['commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
