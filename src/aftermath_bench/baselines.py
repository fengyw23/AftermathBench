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

