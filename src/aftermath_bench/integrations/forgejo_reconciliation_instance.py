from __future__ import annotations

from typing import Any

from .forgejo_promotion_instance import ForgejoPromotionInstanceSpec
from .forgejo_reconciliation_faults import FORGEJO_RECONCILIATION_VARIANTS


def reconciliation_scenario_id(instance: ForgejoPromotionInstanceSpec) -> str:
    prefix = "forgejo-approved-artifact-promotion-"
    suffix = (
        instance.scenario_id.removeprefix(prefix)
        if instance.scenario_id.startswith(prefix)
        else instance.scenario_id
    )
    return f"forgejo-cross-system-reconciliation-{suffix}"


def reconciliation_blueprint(
    instance: ForgejoPromotionInstanceSpec,
    *,
    instance_id: str,
    benchmark_split: str = "public_dev",
) -> dict[str, Any]:
    instance.validate()
    return {
        "schema_version": "0.1-draft",
        "scenario_id": reconciliation_scenario_id(instance),
        "domain_id": "forgejo",
        "instance_id": instance_id,
        "instance_spec_sha256": instance.sha256,
        "family": "forgejo-cross-system-reconciliation",
        "runtime_id": "forgejo-main",
        "benchmark_split": benchmark_split,
        "benchmark_tier": "native_hard_candidate",
        "hidden_test_eligible": benchmark_split == "hidden_test",
        "implementation_status": "native replay validated",
        "title": "Recover independently missing effects of an approved promotion",
        "user_instruction": (
            f"Complete the approved {instance.repository} {instance.version} "
            f"promotion to {instance.production_environment}. The native Actions "
            "bundle must exactly match the approved repository sources; the "
            "artifact registry, production replicas, external transparency "
            "attestation, target release and rollout issue must agree on the "
            f"approved digest {instance.artifact_digest}. Preserve the prior "
            f"release {instance.protected_release_tag}, the protected environment "
            f"{instance.protected_environment}, approval records and unrelated "
            "work. A promotion operation returned a connection error. Determine "
            "which effects actually completed, finish exactly the missing effects, "
            "and do not duplicate valid work."
        ),
        "fixture": instance.as_dict(),
        "ambiguous_operation": {
            "operation": f"dispatch {instance.workflow_path} for {instance.release_tag}",
            "surface_result": "connection closed before the promotion was acknowledged",
        },
        "matched_variants": [
            {
                "id": variant,
                "boundary_class_id": (
                    specification.missing_obligation or "all_effects_valid"
                ),
                "recovery_signature_class": specification.recovery_kind,
            }
            for variant, specification in FORGEJO_RECONCILIATION_VARIANTS.items()
        ],
        "required_semantic_recovery_directions": [
            specification.recovery_kind
            for specification in FORGEJO_RECONCILIATION_VARIANTS.values()
        ],
        "required_public_evidence": [
            "repository approval source contents",
            "native Actions owner and uploaded ZIP entry hashes",
            "deployment artifact registry",
            "production deployment and replicas",
            "external transparency attestation attempts",
            "target and protected releases plus issue state",
        ],
        "public_tool_policy": {
            "ordinary_cross_system_queries": True,
            "ordinary_workflow_and_metadata_mutations": True,
            "global_state_summary": False,
            "recommended_action_tool": False,
            "hidden_variant_label": False,
        },
        "planned_admission_profile": {
            "scope_decision": {
                "minimum_adaptive_worst_case_depth": 6,
                "minimum_static_certificate_size": 6,
            }
        },
    }


__all__ = ["reconciliation_blueprint", "reconciliation_scenario_id"]
