from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any


@dataclass(frozen=True)
class ForgejoPromotionInstanceSpec:
    scenario_id: str
    owner: str
    repository: str
    version: str
    prior_version: str
    approved_commit: str
    workflow_path: str
    approval_manifest_path: str
    binary_path: str
    signature_path: str
    sbom_path: str
    provenance_path: str
    artifact_digest: str
    signer_identity: str
    production_environment: str
    protected_environment: str
    release_tag: str
    protected_release_tag: str
    rollout_issue_title: str
    approval_issue_title: str
    unrelated_issue_title: str
    attestation_key: str

    @classmethod
    def from_path(cls, path: str | Path) -> "ForgejoPromotionInstanceSpec":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        expected = set(cls.__dataclass_fields__)
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError("invalid Forgejo promotion instance fields")
        instance = cls(**{key: str(payload[key]) for key in expected})
        instance.validate()
        return instance

    def validate(self) -> None:
        if any(not value.strip() for value in self.as_dict().values()):
            raise ValueError("Forgejo promotion instance fields must be non-empty")
        if self.version == self.prior_version:
            raise ValueError("target and prior promotion versions must differ")
        if self.release_tag == self.protected_release_tag:
            raise ValueError("target and protected release tags must differ")
        if self.production_environment == self.protected_environment:
            raise ValueError("target and protected environments must differ")
        if not self.artifact_digest.startswith("sha256:"):
            raise ValueError("promotion artifact digest must use sha256")
        expected_digest = hashlib.sha256(
            f"{self.repository} {self.version}\n".encode("utf-8")
        ).hexdigest()
        if self.artifact_digest != f"sha256:{expected_digest}":
            raise ValueError(
                "promotion artifact digest must match the native binary fixture"
            )
        if len(self.approved_commit) != 40 or any(
            character not in "0123456789abcdef" for character in self.approved_commit
        ):
            raise ValueError("approved commit must be a lowercase 40-character SHA")
        paths = (
            self.workflow_path,
            self.approval_manifest_path,
            self.binary_path,
            self.signature_path,
            self.sbom_path,
            self.provenance_path,
        )
        for value in paths:
            path = PurePosixPath(value)
            if path.is_absolute() or ".." in path.parts or "\\" in value:
                raise ValueError(f"unsafe repository path: {value}")
        artifact_paths = {
            self.binary_path,
            self.signature_path,
            self.sbom_path,
            self.provenance_path,
        }
        if len(artifact_paths) != 4:
            raise ValueError("promotion artifact paths must be distinct")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def promotion_blueprint(
    instance: ForgejoPromotionInstanceSpec,
    *,
    instance_id: str = "public-dev-001",
    benchmark_split: str = "public_dev",
) -> dict[str, Any]:
    instance.validate()
    variants = (
        (
            "dispatch_request_not_reached",
            "no_promotion_effect",
            "dispatch_approved_promotion",
        ),
        (
            "workflow_queued_runner_unavailable",
            "promotion_owner_pending",
            "resume_existing_promotion_owner",
        ),
        (
            "signed_bundle_completed_deployment_missing",
            "artifact_effects_committed_deployment_missing",
            "preserve_signed_bundle_deploy_and_publish",
        ),
        (
            "deployment_completed_attestation_missing",
            "deployment_committed_publication_missing",
            "preserve_deployment_publish_attestation",
        ),
        (
            "attestation_accepted_release_metadata_missing",
            "external_effect_committed_release_incomplete",
            "preserve_attestation_close_release_metadata",
        ),
        (
            "promotion_completed_response_lost",
            "all_effects_committed_response_lost",
            "verify_and_preserve_completed_promotion",
        ),
    )
    return {
        "schema_version": "0.1-draft",
        "scenario_id": instance.scenario_id,
        "domain_id": "forgejo",
        "instance_id": instance_id,
        "instance_spec_sha256": instance.sha256,
        "family": "forgejo-approved-artifact-promotion",
        "runtime_id": "forgejo-main",
        "benchmark_split": benchmark_split,
        "benchmark_tier": "unvalidated",
        "hidden_test_eligible": benchmark_split == "hidden_test",
        "implementation_status": "native replay pending",
        "title": (
            "Recover an approved signed-artifact promotion across build, "
            "deployment and external attestation"
        ),
        "user_instruction": (
            f"Complete the approved {instance.repository} {instance.version} "
            f"promotion of commit {instance.approved_commit} to "
            f"{instance.production_environment}. The binary, signature, SBOM and "
            "provenance statement must exactly match the approval manifest and "
            f"approved digest {instance.artifact_digest}. Production must run that "
            "digest, the transparency attestation must be accepted exactly once, "
            "and the target release and rollout issue must close only after those "
            "facts agree. Preserve the completed approval record, previous release "
            f"{instance.protected_release_tag}, {instance.protected_environment}, "
            "and the unrelated open issue. The promotion request returned a "
            "connection error, so reconstruct which effects actually completed."
        ),
        "fixture": instance.as_dict(),
        "ambiguous_operation": {
            "operation": f"dispatch {instance.workflow_path} for {instance.release_tag}",
            "surface_result": (
                "connection closed before the approved promotion was acknowledged"
            ),
        },
        "matched_variants": [
            {
                "id": variant_id,
                "boundary_class_id": boundary,
                "recovery_signature_class": signature,
            }
            for variant_id, boundary, signature in variants
        ],
        "required_semantic_recovery_directions": [
            signature for _, _, signature in variants
        ],
        "required_public_evidence": [
            "approval manifest and approved commit",
            "native Actions run, job and artifact state",
            "binary, signature, SBOM and provenance contents",
            "production deployment digest and rollout state",
            "external transparency attestation and attempt records",
            "target and prior releases",
            "approval, rollout and unrelated issue state",
            "production and protected environment records",
        ],
        "public_tool_policy": {
            "repository_and_approval_reads": True,
            "native_actions_run_job_and_artifact_reads": True,
            "deployment_reads_and_mutations": True,
            "external_attestation_reads_and_mutations": True,
            "release_and_issue_mutations": True,
            "global_state_summary": False,
            "recommended_action_tool": False,
            "hidden_variant_label": False,
        },
        "planned_admission_profile": {
            "scope_decision": {
                "minimum_adaptive_worst_case_depth": 4,
                "minimum_static_certificate_size": 5,
            },
            "obligation_interaction": {
                "minimum_obligation_count": 10,
                "minimum_protected_obligation_count": 4,
                "minimum_gold_scope_count": 6,
                "minimum_cross_obligation_witnesses": 8,
                "minimum_repair_preservation_conflict_witnesses": 5,
                "minimum_variants_with_conflict": 5,
                "minimum_conflicting_action_count": 5,
            },
        },
    }


__all__ = ["ForgejoPromotionInstanceSpec", "promotion_blueprint"]
