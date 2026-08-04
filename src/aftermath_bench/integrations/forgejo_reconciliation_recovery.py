from __future__ import annotations

import base64
import hashlib
import time
from typing import Any

from .deployment_target_api import DeploymentTargetAPI
from .forgejo_api import ForgejoAPI
from .forgejo_promotion_agent import (
    ForgejoPromotionEnvironment,
    inspect_action_artifact,
)
from .forgejo_promotion_evaluator import get_external_delivery
from .forgejo_promotion_instance import ForgejoPromotionInstanceSpec


def collect_reconciliation_state(
    *,
    forgejo: ForgejoAPI,
    deployment: DeploymentTargetAPI,
    instance: ForgejoPromotionInstanceSpec,
    prefix: dict[str, Any],
    external_url: str = "http://127.0.0.1:9092",
) -> dict[str, Any]:
    runs = forgejo.list_action_runs(instance.owner, instance.repository)
    action_artifacts = [
        artifact
        for run in runs
        for artifact in forgejo.list_action_run_artifacts(
            instance.owner, instance.repository, int(run["id"])
        )
    ]
    source_paths = {
        "binary.tar.gz": instance.binary_path,
        "binary.tar.gz.sig": instance.signature_path,
        "artifact.spdx.json": instance.sbom_path,
        "artifact.intoto.jsonl": instance.provenance_path,
    }
    approval_source_manifest = {}
    for archive_name, path in source_paths.items():
        document = forgejo.get_repository_content(
            instance.owner, instance.repository, path=path, ref="main"
        )
        content = base64.b64decode(
            str(document["content"]).replace("\n", ""), validate=True
        )
        approval_source_manifest[archive_name] = {
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    action_artifact_manifests = [
        inspect_action_artifact(
            forgejo,
            owner=instance.owner,
            repository=instance.repository,
            run_id=int(run["id"]),
            artifact_id=int(artifact["id"]),
        )
        for run in runs
        for artifact in forgejo.list_action_run_artifacts(
            instance.owner, instance.repository, int(run["id"])
        )
        if artifact.get("name") == f"approved-{instance.version}"
        and not bool(artifact.get("expired"))
    ]
    issues = forgejo.list_issues(instance.owner, instance.repository)
    comments = forgejo.list_issue_comments(
        instance.owner,
        instance.repository,
        int(prefix["rollout_issue_index"]),
    )
    return {
        "runs": runs,
        "action_artifacts": action_artifacts,
        "action_artifact_manifests": action_artifact_manifests,
        "approval_source_manifest": approval_source_manifest,
        "deployment_state": deployment.state(),
        "external_attestation": get_external_delivery(
            external_url, instance.attestation_key
        ),
        "releases": forgejo.list_releases(instance.owner, instance.repository),
        "issues": issues,
        "comments": comments,
    }


def project_reconciliation_obligations(
    state: dict[str, Any], *, instance: ForgejoPromotionInstanceSpec, prefix: dict[str, Any]
) -> dict[str, bool]:
    deployment_state = state["deployment_state"]
    target_artifacts = [
        row
        for row in deployment_state["artifacts"]
        if row["version"] == instance.version
    ]
    target_deployments = [
        row
        for row in deployment_state["deployments"]
        if row["environment"] == instance.production_environment
    ]
    target_replicas = [
        row
        for row in deployment_state["replicas"]
        if row["environment"] == instance.production_environment
    ]
    attestation = state["external_attestation"]
    target_releases = [
        row for row in state["releases"] if row.get("tag_name") == instance.release_tag
    ]
    rollout = next(
        (
            row
            for row in state["issues"]
            if int(row.get("number", -1)) == int(prefix["rollout_issue_index"])
        ),
        None,
    )
    action_manifests = state["action_artifact_manifests"]
    expected_manifest = state["approval_source_manifest"]
    observed_manifest = (
        {
            str(row["name"]): {
                "size": int(row["size"]),
                "sha256": str(row["sha256"]),
            }
            for row in action_manifests[0]["files"]
        }
        if len(action_manifests) == 1
        else {}
    )
    actions_valid = len(action_manifests) == 1 and observed_manifest == expected_manifest
    registry_valid = (
        len(target_artifacts) == 1
        and target_artifacts[0]["digest"] == instance.artifact_digest
        and target_artifacts[0]["source_commit"] == instance.approved_commit
        and int(target_artifacts[0]["attempt_count"]) == 1
    )
    production_valid = (
        len(target_deployments) == 1
        and target_deployments[0]["desired_version"] == instance.version
        and target_deployments[0]["artifact_digest"] == instance.artifact_digest
        and target_deployments[0]["status"] == "deployed"
        and len(target_replicas) == 2
        and all(
            row["version"] == instance.version
            and row["artifact_digest"] == instance.artifact_digest
            and row["status"] == "ready"
            for row in target_replicas
        )
    )
    attestation_valid = (
        isinstance(attestation, dict)
        and int(attestation.get("attempt_count", 0)) == 1
        and attestation.get("payload", {}).get("artifact_digest")
        == instance.artifact_digest
    )
    metadata_valid = (
        len(target_releases) == 1
        and rollout is not None
        and rollout.get("state") == "closed"
    )
    return {
        "actions_bundle_matches_approval": actions_valid,
        "artifact_registry_matches_bundle": registry_valid,
        "production_matches_registry": production_valid,
        "attestation_matches_production": attestation_valid,
        "release_metadata_matches_all_effects": metadata_valid,
    }


def evaluate_reconciliation_terminal(
    state: dict[str, Any], *, instance: ForgejoPromotionInstanceSpec, prefix: dict[str, Any]
) -> dict[str, Any]:
    obligations = project_reconciliation_obligations(
        state, instance=instance, prefix=prefix
    )
    deployment_state = state["deployment_state"]
    protected_deployments = [
        row
        for row in deployment_state["deployments"]
        if row["environment"] == instance.protected_environment
    ]
    protected_replicas = [
        row
        for row in deployment_state["replicas"]
        if row["environment"] == instance.protected_environment
    ]
    preservation = {
        "protected_deployment_preserved": protected_deployments
        == [
            row
            for row in prefix["protected_state"]["deployments"]
            if row["environment"] == instance.protected_environment
        ],
        "protected_replicas_preserved": protected_replicas
        == [
            row
            for row in prefix["protected_state"]["replicas"]
            if row["environment"] == instance.protected_environment
        ],
        "prior_release_preserved": sum(
            row.get("tag_name") == instance.protected_release_tag
            for row in state["releases"]
        )
        == 1,
    }
    checks = {**obligations, **preservation}
    return {
        "passed": all(checks.values()),
        "components": {
            "goal_completion": all(obligations.values()),
            "repair_completeness": all(obligations.values()),
            "preservation": all(preservation.values()),
            "protocol_safety": all(obligations.values()),
        },
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "obligation_projection": obligations,
    }


def reference_reconciliation_recovery(
    environment: ForgejoPromotionEnvironment,
) -> list[dict[str, Any]]:
    """Repair only obligations proven missing by the public cross-system state."""

    spec = environment.instance
    prefix = environment.prefix

    def state() -> dict[str, Any]:
        return collect_reconciliation_state(
            forgejo=environment.forgejo,
            deployment=environment.deployment,
            instance=spec,
            prefix=prefix,
            external_url=environment.external_url,
        )

    def dispatch(inputs: dict[str, str]) -> None:
        before = {
            int(row["id"])
            for row in environment.forgejo.list_action_runs(spec.owner, spec.repository)
        }
        environment.invoke(
            "dispatch_workflow",
            workflow=spec.workflow_path,
            ref="main",
            inputs=inputs,
        )
        created: list[dict[str, Any]] = []
        for attempt in range(40):
            runs = environment.forgejo.list_action_runs(spec.owner, spec.repository)
            created = [row for row in runs if int(row["id"]) not in before]
            if created:
                break
            if attempt + 1 < 40:
                time.sleep(0.25)
        if len(created) != 1:
            raise RuntimeError(f"targeted recovery created {len(created)} owners")
        environment.invoke(
            "wait_for_action_run", run_id=int(created[0]["id"]), timeout_seconds=60
        )

    environment.invoke("start_action_runner")
    obligations = project_reconciliation_obligations(
        state(), instance=spec, prefix=prefix
    )
    if not obligations["actions_bundle_matches_approval"]:
        dispatch({"resume_stage": "start", "stop_after": "artifact"})
    if not obligations["artifact_registry_matches_bundle"]:
        dispatch({"resume_stage": "after_artifact", "stop_after": "bundle"})
    if not obligations["production_matches_registry"]:
        dispatch({"resume_stage": "after_bundle", "stop_after": "deployment"})
    if not obligations["attestation_matches_production"]:
        dispatch({"resume_stage": "after_deployment", "stop_after": "none"})
    if not obligations["release_metadata_matches_all_effects"]:
        environment.invoke(
            "create_release",
            tag=spec.release_tag,
            target="main",
            title=f"{spec.repository} {spec.version}",
            body=(
                f"Production digest {spec.artifact_digest}; transparency "
                f"attestation {spec.attestation_key}."
            ),
        )
        environment.invoke(
            "edit_issue", index=int(prefix["rollout_issue_index"]), state="closed"
        )
    state()
    return environment.event_log()


__all__ = [
    "collect_reconciliation_state",
    "evaluate_reconciliation_terminal",
    "project_reconciliation_obligations",
    "reference_reconciliation_recovery",
]
