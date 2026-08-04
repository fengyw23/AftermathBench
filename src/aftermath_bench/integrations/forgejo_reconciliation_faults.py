from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ForgejoReconciliationVariant:
    missing_obligation: str | None
    recovery_kind: str
    recovery_workflow_inputs: dict[str, str] | None


FORGEJO_RECONCILIATION_VARIANTS: dict[str, ForgejoReconciliationVariant] = {
    "all_effects_valid_response_lost": ForgejoReconciliationVariant(
        missing_obligation=None,
        recovery_kind="verify_and_preserve",
        recovery_workflow_inputs=None,
    ),
    "actions_bundle_missing": ForgejoReconciliationVariant(
        missing_obligation="actions_bundle_matches_approval",
        recovery_kind="repair_actions_bundle_only",
        recovery_workflow_inputs={
            "resume_stage": "start",
            "stop_after": "artifact",
        },
    ),
    "artifact_registry_missing": ForgejoReconciliationVariant(
        missing_obligation="artifact_registry_matches_bundle",
        recovery_kind="repair_artifact_registry_only",
        recovery_workflow_inputs={
            "resume_stage": "after_artifact",
            "stop_after": "bundle",
        },
    ),
    "production_deployment_missing": ForgejoReconciliationVariant(
        missing_obligation="production_matches_registry",
        recovery_kind="repair_production_only",
        recovery_workflow_inputs={
            "resume_stage": "after_bundle",
            "stop_after": "deployment",
        },
    ),
    "external_attestation_missing": ForgejoReconciliationVariant(
        missing_obligation="attestation_matches_production",
        recovery_kind="repair_attestation_only",
        recovery_workflow_inputs={
            "resume_stage": "after_deployment",
            "stop_after": "none",
        },
    ),
    "release_metadata_missing": ForgejoReconciliationVariant(
        missing_obligation="release_metadata_matches_all_effects",
        recovery_kind="repair_release_metadata_only",
        recovery_workflow_inputs=None,
    ),
}


def reconciliation_scope_matrix() -> dict[str, object]:
    obligations = tuple(
        item.missing_obligation
        for item in FORGEJO_RECONCILIATION_VARIANTS.values()
        if item.missing_obligation is not None
    )
    return {
        "schema_version": "1.0-design",
        "scenario_id": "forgejo-cross-system-reconciliation-dev-001",
        "surface_requirements": {
            "actions_bundle_matches_approval": [
                "approval_manifest",
                "actions_artifact",
            ],
            "artifact_registry_matches_bundle": [
                "actions_artifact",
                "deployment_artifact_registry",
            ],
            "production_matches_registry": [
                "deployment_artifact_registry",
                "production_deployment",
            ],
            "attestation_matches_production": [
                "production_deployment",
                "external_attestation",
            ],
            "release_metadata_matches_all_effects": [
                "approval_manifest",
                "production_deployment",
                "external_attestation",
                "release_metadata",
            ],
        },
        "rows": [
            {
                "variant": variant,
                "recovery_signature": specification.recovery_kind,
                "observations": {
                    obligation: obligation != specification.missing_obligation
                    for obligation in obligations
                },
            }
            for variant, specification in FORGEJO_RECONCILIATION_VARIANTS.items()
        ],
    }


__all__ = [
    "FORGEJO_RECONCILIATION_VARIANTS",
    "ForgejoReconciliationVariant",
    "reconciliation_scope_matrix",
]
