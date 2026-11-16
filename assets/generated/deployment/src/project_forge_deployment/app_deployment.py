"""Isolation-aware application deployment orchestration.

The low-level application runtime owns immutable container mechanics. This module
binds those mechanics to the broader read-only environment isolation contract so
real application deployment plans cannot ignore route, persistence, or sibling
ownership changes that occur after human review.
"""

from __future__ import annotations

from typing import Any, Iterable

from .app_runtime import PRODUCTION_APP_DEPLOY_WRITE_PHRASE
from .app_runtime import apply_app_deploy as _apply_runtime_deploy
from .app_runtime import deploy_write_phrase
from .app_runtime import plan_app_deploy as _plan_runtime_deploy
from .app_runtime import render_locked_app_deploy_stage as _render_locked_runtime_deploy_stage
from .app_runtime_workstation import apply_app_deploy_with_preloaded_image
from .environment_isolation import environment_isolation_preflight
from .errors import DeploymentKitError
from .image_transfer import transfer_image
from .route_registry import ROUTE_WRITE_PHRASE, plan_route_registration


ISOLATION_REVIEW_KEY = "isolationReview"
ROLLOUT_SCHEMA_VERSION = 1


def app_isolation_check(
    target_name: str,
    *,
    owner_repo: str,
    environment: str,
    production: bool = False,
    app_slug: str,
    container_name: str,
    runtime_port: int,
    persistence_mode: str,
    database_file: str | None = None,
    route_hostnames: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return read-only isolation evidence for a real application footprint."""

    return environment_isolation_preflight(
        target_name,
        owner_repo=owner_repo,
        environment=environment,
        production=production,
        app_slug=app_slug,
        container_name=container_name,
        runtime_port=runtime_port,
        persistence_mode=persistence_mode,
        database_file=database_file,
        route_hostnames=route_hostnames,
        require_vacant_app_identity=False,
    )


def _check_from_spec(
    target_name: str,
    spec: dict[str, Any],
    *,
    production: bool,
    database_file: str | None,
    route_hostnames: Iterable[str] | None,
) -> dict[str, Any]:
    return app_isolation_check(
        target_name,
        owner_repo=spec["ownerRepo"],
        environment=spec["environment"],
        production=production,
        app_slug=spec["appSlug"],
        container_name=spec["containerName"],
        runtime_port=spec["runtimePort"],
        persistence_mode=spec["persistence"]["mode"],
        database_file=database_file,
        route_hostnames=route_hostnames,
    )


def _require_clear(isolation: dict[str, Any], *, context: str) -> None:
    if isolation.get("state") == "clear":
        return
    conflicts = isolation.get("conflicts") or []
    codes = sorted(
        {
            item.get("code", "unknown-collision")
            for item in conflicts
            if isinstance(item, dict)
        }
    )
    detail = ", ".join(codes) if codes else "unspecified collision"
    raise DeploymentKitError(
        f"Application isolation {context} is blocked: {detail}. Resolve the collision before deployment."
    )


def _review(isolation: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": isolation["schemaVersion"],
        "targetName": isolation["targetName"],
        "ownerRepo": isolation["ownerRepo"],
        "environment": isolation["environment"],
        "production": isolation["production"],
        "state": isolation["state"],
        "sharedFailureDomain": isolation["sharedFailureDomain"],
        "siblingEnvironments": isolation["siblingEnvironments"],
        "desired": isolation["desired"],
        "checks": isolation["checks"],
        "conflicts": isolation["conflicts"],
        "inventorySnapshots": isolation["inventorySnapshots"],
        "evidenceSha256": isolation["evidenceSha256"],
    }


def _runtime_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict) or ISOLATION_REVIEW_KEY not in plan:
        raise DeploymentKitError("Application deployment plan is missing reviewed isolation evidence.")
    return {key: value for key, value in plan.items() if key != ISOLATION_REVIEW_KEY}


def plan_app_deploy(
    target_name: str,
    spec: dict[str, Any],
    *,
    production: bool = False,
    database_file: str | None = None,
    route_hostnames: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Plan a real application deployment with current isolation evidence."""

    runtime_plan = _plan_runtime_deploy(target_name, spec)
    isolation = _check_from_spec(
        target_name,
        spec,
        production=production,
        database_file=database_file,
        route_hostnames=route_hostnames,
    )
    _require_clear(isolation, context="preflight")

    plan = dict(runtime_plan)
    plan[ISOLATION_REVIEW_KEY] = _review(isolation)
    return plan


def _endpoint_states(route_plan: dict[str, Any] | None) -> dict[str, str]:
    if route_plan is None:
        return {
            "beforeRuntime": "NO_ROUTE_REQUESTED",
            "afterRuntimeBeforeRoute": "NO_ROUTE_REQUESTED",
            "afterRoute": "NO_ROUTE_REQUESTED",
        }
    if route_plan["changeType"] == "create":
        before = "NOT_ACTIVE_ROUTE_ABSENT"
        after_runtime = "NOT_ACTIVE_ROUTE_PENDING"
    else:
        before = "ROUTE_PRESENT_RUNTIME_STATE_NOT_VALIDATED"
        after_runtime = "ROUTE_PRESENT_ROUTE_CHANGE_PENDING"
    return {
        "beforeRuntime": before,
        "afterRuntimeBeforeRoute": after_runtime,
        "afterRoute": "ROUTE_REGISTERED_BROWSER_VERIFICATION_PENDING",
    }


def plan_app_rollout(
    target_name: str,
    spec: dict[str, Any],
    *,
    production: bool = False,
    database_file: str | None = None,
    route_hostnames: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Compose read-only runtime and route plans into one staged rollout preview."""

    hosts = list(route_hostnames or [])
    app_plan = plan_app_deploy(
        target_name,
        spec,
        production=production,
        database_file=database_file,
        route_hostnames=hosts,
    )
    route_plan = None
    if hosts:
        route_plan = plan_route_registration(
            target_name,
            owner_repo=spec["ownerRepo"],
            environment=spec["environment"],
            app_slug=spec["appSlug"],
            upstream_container=spec["containerName"],
            upstream_port=spec["runtimePort"],
            hostnames=hosts,
        )

    runtime_authorization = (
        PRODUCTION_APP_DEPLOY_WRITE_PHRASE
        if production or spec["environment"] == "production"
        else deploy_write_phrase(app_plan)
    )
    stages = [
        {
            "stage": "runtime",
            "action": "deploy-application-runtime",
            "requiredAuthorization": runtime_authorization,
            "mutated": False,
        }
    ]
    if route_plan is not None:
        stages.append(
            {
                "stage": "route",
                "action": "register-application-route",
                "requiredAuthorization": ROUTE_WRITE_PHRASE,
                "mutated": False,
            }
        )

    runtime_view = {key: value for key, value in app_plan.items() if key != "spec"}
    return {
        "schemaVersion": ROLLOUT_SCHEMA_VERSION,
        "targetName": target_name,
        "environment": spec["environment"],
        "production": bool(production or spec["environment"] == "production"),
        "image": spec["image"],
        "runtimePlan": runtime_view,
        "routePlan": route_plan,
        "stages": stages,
        "separateAuthorizationsRequired": route_plan is not None,
        "endpointState": _endpoint_states(route_plan),
        "postRouteVerification": (
            ["application-health", "route-http", "workstation-browser"]
            if route_plan is not None
            else ["application-health"]
        ),
        "mutated": False,
    }


def revalidate_app_isolation(plan: dict[str, Any]) -> dict[str, Any]:
    """Recheck the reviewed application footprint immediately before mutation."""

    runtime_plan = _runtime_plan(plan)
    review = plan[ISOLATION_REVIEW_KEY]
    if not isinstance(review, dict):
        raise DeploymentKitError("Application deployment plan has malformed isolation evidence.")
    desired = review.get("desired")
    if not isinstance(desired, dict):
        raise DeploymentKitError("Application deployment plan has malformed isolation desired state.")

    current = _check_from_spec(
        runtime_plan["targetName"],
        runtime_plan["spec"],
        production=bool(review.get("production")),
        database_file=desired.get("databaseFile"),
        route_hostnames=desired.get("routeHostnames") or [],
    )
    _require_clear(current, context="recheck")

    reviewed_sha = review.get("evidenceSha256")
    if not isinstance(reviewed_sha, str) or current["evidenceSha256"] != reviewed_sha:
        raise DeploymentKitError(
            "Application isolation state changed after the plan was reviewed; create and authorize a fresh plan."
        )
    return current


def apply_app_deploy(plan: dict[str, Any]) -> dict[str, Any]:
    """Apply a registry-backed runtime plan after isolation revalidation."""

    revalidate_app_isolation(plan)
    return _apply_runtime_deploy(_runtime_plan(plan))


def render_locked_app_deploy_stage(
    plan: dict[str, Any], *, inherited_lock_fd: int, authorization: str,
) -> dict[str, str]:
    """Render a registry-backed deploy stage after isolation revalidation."""

    runtime_plan = _runtime_plan(plan)
    review = plan[ISOLATION_REVIEW_KEY]
    if not isinstance(review, dict) or type(review.get("production")) is not bool:
        raise DeploymentKitError("Application deployment plan has malformed Production classification.")
    production = review["production"] or runtime_plan["environment"] == "production"
    expected_authorization = (
        PRODUCTION_APP_DEPLOY_WRITE_PHRASE if production else deploy_write_phrase(runtime_plan)
    )
    if authorization != expected_authorization:
        raise DeploymentKitError("Exact reviewed application deployment authorization phrase is required.")
    revalidate_app_isolation(plan)
    return _render_locked_runtime_deploy_stage(
        runtime_plan,
        inherited_lock_fd=inherited_lock_fd,
        authorization=authorization,
        production=production,
    )


def apply_app_deploy_from_workstation(plan: dict[str, Any]) -> dict[str, Any]:
    """Transfer an exact image, then recheck isolation again before runtime mutation."""

    revalidate_app_isolation(plan)
    runtime_plan = _runtime_plan(plan)
    transfer = transfer_image(runtime_plan["targetName"], runtime_plan["image"])
    revalidate_app_isolation(plan)
    return apply_app_deploy_with_preloaded_image(runtime_plan, transfer)


__all__ = [
    "ISOLATION_REVIEW_KEY",
    "ROLLOUT_SCHEMA_VERSION",
    "app_isolation_check",
    "apply_app_deploy",
    "apply_app_deploy_from_workstation",
    "plan_app_deploy",
    "plan_app_rollout",
    "revalidate_app_isolation",
    "render_locked_app_deploy_stage",
]
