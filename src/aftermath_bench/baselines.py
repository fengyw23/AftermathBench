from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .scenarios.release_migration import (
    RELEASE_VARIANTS,
    ReleaseMigrationEnv,
    build_release_failure_state,
    evaluate_release,
    reference_release_recovery,
)
from .scenarios.itsm_major_incident import (
    ITSM_VARIANTS,
    ITSMMajorIncidentEnv,
    build_itsm_failure_state,
    evaluate_itsm,
    reference_itsm_recovery,
)

ReleasePolicy = Callable[[ReleaseMigrationEnv], None]


def _finalize_release(environment: ReleaseMigrationEnv) -> None:
    version = environment.VERSION
    environment.invoke("record_recovery_audit", version=version)
    environment.invoke("send_release_notification", version=version)
    environment.invoke("close_change_request", change_id="chg-204")


def blind_retry(environment: ReleaseMigrationEnv) -> None:
    environment.invoke("deploy_release", version=environment.VERSION)
    _finalize_release(environment)


def assume_committed(environment: ReleaseMigrationEnv) -> None:
    _finalize_release(environment)


def query_deployment_only(environment: ReleaseMigrationEnv) -> None:
    deployment = environment.invoke("get_deployment")["data"]
    if deployment["status"] != "healthy":
        environment.invoke("deploy_release", version=environment.VERSION)
    _finalize_release(environment)


def investigate_and_repair(environment: ReleaseMigrationEnv) -> None:
    reference_release_recovery(environment)


RELEASE_BASELINES: dict[str, ReleasePolicy] = {
    "blind_retry": blind_retry,
    "assume_committed": assume_committed,
    "query_deployment_only": query_deployment_only,
    "investigate_and_repair": investigate_and_repair,
}


def run_release_baselines() -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for name, policy in RELEASE_BASELINES.items():
        variants: dict[str, bool] = {}
        for variant in RELEASE_VARIANTS:
            environment, _proxy, _failure = build_release_failure_state(variant)
            try:
                policy(environment)
                variants[variant] = evaluate_release(environment.snapshot())["passed"]
            finally:
                environment.close()
        report[name] = {
            "passed": sum(variants.values()),
            "total": len(variants),
            "matched_group_success": all(variants.values()),
            "variants": variants,
        }
    return report


ITSMPolicy = Callable[[ITSMMajorIncidentEnv], None]


def _finalize_itsm(environment: ITSMMajorIncidentEnv) -> None:
    incident_id = environment.INCIDENT_ID
    environment.invoke("record_escalation_audit", incident_id=incident_id)
    environment.invoke("send_caller_update", incident_id=incident_id)
    environment.invoke(
        "close_escalation_review",
        review_id="review-001",
        incident_id=incident_id,
    )


def itsm_blind_retry(environment: ITSMMajorIncidentEnv) -> None:
    environment.invoke(
        "escalate_major_incident",
        incident_id=environment.INCIDENT_ID,
    )
    _finalize_itsm(environment)


def itsm_assume_committed(environment: ITSMMajorIncidentEnv) -> None:
    _finalize_itsm(environment)


def itsm_query_incident_only(environment: ITSMMajorIncidentEnv) -> None:
    incident = environment.invoke(
        "find_incident",
        incident_id=environment.INCIDENT_ID,
    )["data"]
    if incident["priority"] != 1:
        environment.invoke(
            "escalate_major_incident",
            incident_id=environment.INCIDENT_ID,
        )
    _finalize_itsm(environment)


def itsm_investigate_and_repair(environment: ITSMMajorIncidentEnv) -> None:
    reference_itsm_recovery(environment)


ITSM_BASELINES: dict[str, ITSMPolicy] = {
    "blind_retry": itsm_blind_retry,
    "assume_committed": itsm_assume_committed,
    "query_incident_only": itsm_query_incident_only,
    "investigate_and_repair": itsm_investigate_and_repair,
}


def run_itsm_baselines() -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for name, policy in ITSM_BASELINES.items():
        variants: dict[str, bool] = {}
        for variant in ITSM_VARIANTS:
            environment, _proxy, _failure = build_itsm_failure_state(variant)
            try:
                policy(environment)
                variants[variant] = evaluate_itsm(environment)["passed"]
            finally:
                environment.close()
        report[name] = {
            "passed": sum(variants.values()),
            "total": len(variants),
            "matched_group_success": all(variants.values()),
            "variants": variants,
        }
    return report
