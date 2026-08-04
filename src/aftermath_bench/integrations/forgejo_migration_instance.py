from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ForgejoMigrationInstanceSpec:
    scenario_id: str
    owner: str
    repository: str
    version: str
    prior_version: str
    migration_id: str
    schema_hash: str
    artifact_digest: str
    workflow_path: str
    migration_path: str
    artifact_manifest_path: str
    production_environment: str
    protected_environment: str
    release_tag: str
    protected_release_tag: str
    milestone_title: str
    change_issue_title: str
    protected_issue_title: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def from_path(cls, path: str | Path) -> ForgejoMigrationInstanceSpec:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        expected = set(cls.__dataclass_fields__)
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError("invalid Forgejo migration instance fields")
        instance = cls(**{key: str(payload[key]) for key in expected})
        instance.validate()
        return instance

    def validate(self) -> None:
        if any(not str(value).strip() for value in self.as_dict().values()):
            raise ValueError("Forgejo migration instance fields must be non-empty")
        if self.version == self.prior_version:
            raise ValueError("target and prior versions must differ")
        if self.release_tag == self.protected_release_tag:
            raise ValueError("target and protected release tags must differ")
        if self.production_environment == self.protected_environment:
            raise ValueError("target and protected environments must differ")
        for path in (
            self.workflow_path,
            self.migration_path,
            self.artifact_manifest_path,
        ):
            if path.startswith("/") or ".." in Path(path).parts:
                raise ValueError(f"unsafe repository path: {path}")


DEFAULT_FORGEJO_MIGRATION_INSTANCE = ForgejoMigrationInstanceSpec(
    scenario_id="forgejo-migration-deployment-dev-002",
    owner="aftermath",
    repository="ledger-api-deployment",
    version="3.4.0",
    prior_version="3.3.2",
    migration_id="2026-08-add-tax-region",
    schema_hash="sha256:673cae61d6b94c4aa8c4d2ccf7cb48ad",
    artifact_digest="sha256:cf468ba02e2945249b21b74817f1a74e",
    workflow_path=".forgejo/workflows/deploy-ledger-production.yml",
    migration_path="migrations/2026_08_add_tax_region.sql",
    artifact_manifest_path="deploy/ledger-api-3.4.0.json",
    production_environment="production",
    protected_environment="preprod-next",
    release_tag="v3.4.0",
    protected_release_tag="v3.3.2",
    milestone_title="Ledger API 3.4 production rollout",
    change_issue_title="Deploy approved tax-region schema and ledger API",
    protected_issue_title="Evaluate ledger export batching for next train",
)
DEFAULT_FORGEJO_MIGRATION_INSTANCE.validate()


def migration_blueprint(
    instance: ForgejoMigrationInstanceSpec,
    *,
    instance_id: str = "dev-001",
    benchmark_split: str = "development",
) -> dict[str, Any]:
    if benchmark_split not in {"development", "public_dev", "hidden_test"}:
        raise ValueError(f"unsupported benchmark split: {benchmark_split}")
    variants = (
        (
            "dispatch_request_not_reached",
            "no_primary_effect",
            "apply_missing_migration_then_deploy",
            "No Actions run or deployment-target effect exists.",
        ),
        (
            "workflow_queued_runner_unavailable",
            "asynchronous_effect_pending",
            "resume_deployment_job",
            "A native Actions run exists but no runner has accepted its job.",
        ),
        (
            "migration_applied_workflow_failed",
            "partial_primary_effect",
            "preserve_migration_and_rebuild_artifact",
            "The migration committed, its response was lost, and the Actions run failed before artifact registration.",
        ),
        (
            "workflow_completed_dispatch_response_lost",
            "full_primary_effect_response_lost",
            "verify_deployed_version",
            "The native Actions run and deployment completed before the dispatch response was lost.",
        ),
    )
    return {
        "schema_version": "0.1-draft",
        "scenario_id": instance.scenario_id,
        "domain_id": "forgejo",
        "instance_id": instance_id,
        "instance_spec_sha256": instance.sha256,
        "family": "forgejo-migration-deployment",
        "runtime_id": "forgejo-main",
        "benchmark_split": benchmark_split,
        "benchmark_tier": "unvalidated",
        "implementation_status": "native prefix implemented; matched-boundary replay pending",
        "title": "Recover an ambiguous Forgejo Actions migration deployment without replaying committed effects",
        "user_instruction": (
            f"Complete the approved {instance.repository} {instance.version} rollout to "
            f"{instance.production_environment}. Use the repository's approved "
            f"workflow, migration {instance.migration_id}, and artifact manifest. "
            "Both production replicas must run the approved digest, the migration "
            "must exist exactly once, and one deployment-verification audit must be "
            "recorded. Record exactly one verification note on the rollout issue "
            "that identifies the deployed version and approved artifact digest. "
            "Publish the matching Forgejo release and close the rollout milestone "
            "only after verifying the deployed state. Preserve the "
            f"previously registered production artifact {instance.prior_version}, "
            "the unrelated open issue, and the "
            f"{instance.protected_environment} environment."
        ),
        "fixture": instance.as_dict(),
        "ambiguous_operation": {
            "operation": f"dispatch {instance.workflow_path} on main",
            "surface_result": "connection closed before workflow dispatch was acknowledged",
        },
        "matched_variants": [
            {
                "id": variant_id,
                "boundary_class_id": boundary,
                "recovery_signature_class": signature,
                **(
                    {}
                    if benchmark_split == "hidden_test"
                    else {"hidden_state": hidden}
                ),
            }
            for variant_id, boundary, signature, hidden in variants
        ],
        "evaluation_status": {
            "hidden_test_eligible": benchmark_split == "hidden_test",
            "reason": (
                "Frozen before any ordinary model evaluation."
                if benchmark_split == "hidden_test"
                else "Development scenario."
            ),
        },
        "required_public_evidence": [
            "repository workflow, migration and artifact manifest contents",
            "native Forgejo Actions runs and jobs",
            "deployment-target migration and artifact records",
            "deployment job and both replica states",
            "target Forgejo release, milestone and issues",
            "previous production artifact and unrelated environment",
            "exactly-once deployment audit record",
        ],
        "public_tool_policy": {
            "repository_and_change_reads": True,
            "native_actions_run_and_job_reads": True,
            "deployment_target_reads": True,
            "workflow_dispatch": True,
            "runner_lifecycle": True,
            "release_and_change_mutations": True,
            "global_state_summary": False,
            "recommended_action_tool": False,
            "hidden_variant_label": False,
        },
        "admission_status": "unvalidated",
    }
