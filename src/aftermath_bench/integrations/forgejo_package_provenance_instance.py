from __future__ import annotations

from typing import Any

from .forgejo_publication_instance import ForgejoPublicationInstanceSpec


def package_provenance_blueprint(
    instance: ForgejoPublicationInstanceSpec,
    *,
    instance_id: str,
    benchmark_split: str,
    hidden_test_eligible: bool,
    generation: str = "r1",
) -> dict[str, Any]:
    """Render one package-provenance scenario from a fresh native instance."""

    instance.validate()
    if not instance_id.strip():
        raise ValueError("instance_id must be non-empty")
    if benchmark_split not in {"development", "public_dev", "hidden_test"}:
        raise ValueError(f"unsupported benchmark split: {benchmark_split}")
    if hidden_test_eligible is not (benchmark_split == "hidden_test"):
        raise ValueError("hidden_test_eligible must agree with benchmark_split")
    if generation not in {"r1", "r2"}:
        raise ValueError(f"unsupported package-provenance generation: {generation}")

    protected_version = instance.protected_release_tag.removeprefix("v")
    r1_variants = (
        (
            "package_request_not_reached",
            "no_primary_effect",
            "publish_missing_version",
        ),
        (
            "package_binary_committed_response_lost",
            "primary_effect_uncertain",
            "preserve_blob_and_attach_metadata",
        ),
        (
            "package_complete_index_missing",
            "downstream_effect_missing",
            "resume_indexing",
        ),
        (
            "package_complete_index_accepted_response_lost",
            "downstream_effect_pending_or_accepted",
            "verify_complete_package",
        ),
    )
    r2_variants = (
        (
            "r2_package_request_not_reached",
            "no_primary_effect",
            "create_missing_package_chain",
        ),
        (
            "r2_package_binary_committed_response_lost",
            "primary_effect_uncertain",
            "preserve_valid_partial_package",
        ),
        (
            "r2_package_complete_index_missing",
            "same_inventory_valid_content",
            "preserve_complete_package_and_create_index",
        ),
        (
            "r2_package_corrupt_binary_index_missing",
            "same_inventory_invalid_content",
            "replace_invalid_package_and_create_index",
        ),
    )
    variants = r1_variants if generation == "r1" else r2_variants
    return {
        "schema_version": "0.8-draft" if generation == "r2" else "0.7-draft",
        "scenario_id": instance.scenario_id,
        "domain_id": "forgejo",
        "instance_id": instance_id,
        "instance_spec_sha256": instance.sha256,
        "family": "forgejo-package-provenance",
        "runtime_id": "forgejo-main",
        "benchmark_split": benchmark_split,
        "benchmark_tier": "unvalidated",
        "evaluation_status": {
            "hidden_test_eligible": hidden_test_eligible,
            "reason": (
                "Frozen before any ordinary model evaluation."
                if hidden_test_eligible
                else "Public development instance."
            ),
        },
        "implementation_status": (
            "native non-monotonic package replay and strict admission pending"
            if generation == "r2"
            else "adaptive native package replay and strict admission pending"
        ),
        "title": (
            "Recover an interrupted package version, provenance and "
            "downstream index chain"
        ),
        "user_instruction": (
            f"Complete publication of {instance.package_name} "
            f"{instance.version} as one Forgejo Generic Package version "
            "with exactly the approved binary, checksum, Sigstore bundle "
            f"and SPDX SBOM declared by the approval records on "
            f"{instance.base_branch}. Preserve the linked repository "
            f"approval, existing {protected_version} package and release, "
            f"and unrelated work on {instance.protected_branch}. Ensure "
            "the completed package has exactly one repository index Release "
            f"and that both {instance.coordinator_consumer} and "
            f"{instance.provenance_consumer} receive the corresponding "
            "release effect exactly once. Close the package tracking issues "
            "and milestone only after their stated file, index and delivery "
            "obligations hold. Determine what committed after the connection "
            "failure from authoritative package, repository, webhook and "
            "receiver state; do not repeat valid effects."
        ),
        "fixture": {
            "owner": instance.owner,
            "repository": instance.repository,
            "package_name": instance.package_slug,
            "package_version": instance.version,
            "protected_package_version": protected_version,
            "base_branch": instance.base_branch,
            "package_index_release_tag": instance.release_tag,
        },
        "ambiguous_operation": {
            "operation": (
                "publish the approved Generic Package version and provenance chain"
            ),
            "surface_result": (
                "HTTP connection lost before package publication completion "
                "was acknowledged"
            ),
        },
        "matched_variants": [
            {
                "id": variant_id,
                "boundary_class_id": boundary_class_id,
                "recovery_signature_class": recovery_signature_class,
            }
            for variant_id, boundary_class_id, recovery_signature_class in variants
        ],
        "required_semantic_recovery_directions": [
            recovery_signature_class for _, _, recovery_signature_class in variants
        ],
        "required_public_evidence": [
            "approval and tracking issues that identify the manifest and obligations",
            "repository manifest followed by its approved source files",
            "native package version and attached file contents",
            "repository index Release and milestone state",
            "webhook inventory followed by per-hook native delivery histories",
            "exact receiver records discovered from native delivery UUIDs",
            "protected prior package, release, Pull Request, issue and branch rule",
        ],
        "public_tool_policy": {
            "ordinary_package_reads": True,
            "ordinary_repository_reads": True,
            "native_package_uploads": True,
            "ordinary_release_and_webhook_reads": True,
            "ordinary_receiver_reads": True,
            "global_state_summary": False,
            "recommended_action_tool": False,
            "hidden_variant_label": False,
        },
        "admission_profile": {
            "adaptive_recovery": {
                "minimum_adaptive_query_depth": 4 if generation == "r2" else 3,
                "minimum_variant_specific_mutations": 3 if generation == "r2" else 2,
                "minimum_pairwise_mutation_distance": 3 if generation == "r2" else 2,
                **(
                    {
                        "requires_same_inventory_opposite_scope_pair": True,
                        "requires_non_monotonic_repair": True,
                    }
                    if generation == "r2"
                    else {}
                ),
            }
        },
        "admission_status": "unvalidated",
    }


__all__ = ["package_provenance_blueprint"]
