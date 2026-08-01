from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


INSTANCE_ENVIRONMENT_VARIABLE = (
    "AFTERMATH_KUBERNETES_INTERACTION_INSTANCE_SPEC"
)

_DNS_LABEL = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
_LABEL_VALUE = re.compile(
    r"^(?:[A-Za-z0-9](?:[-_.A-Za-z0-9]*[A-Za-z0-9])?)?$"
)


@dataclass(frozen=True)
class KubernetesInteractionInstanceSpec:
    """Frozen business identities and scalar facts for one native instance."""

    scenario_id: str
    namespace: str
    application: str
    change_stem: str
    current_version: str
    target_version: str
    current_epoch: str
    target_epoch: str
    current_credential_generation: str
    target_credential_generation: str
    batch_id: str
    api_service: str
    current_api_deployment: str
    target_api_deployment: str
    current_worker_deployment: str
    target_worker_deployment: str
    current_credential: str
    next_credential: str
    backup_job: str
    migration_generate_name: str
    transition_job: str
    publication_job: str
    service_account: str
    observer_role: str
    schema_contract: str
    compatibility_contract: str
    credential_contract: str
    controller_contract: str
    publication_contract: str
    audit_contract: str
    database_catalog: str
    compatibility_bridge: str
    batch_state: str
    change_record: str
    release_ledger: str
    recovery_audit: str

    @property
    def current_change_id(self) -> str:
        return f"{self.change_stem}-{self.current_version}"

    @property
    def target_change_id(self) -> str:
        return f"{self.change_stem}-{self.target_version}"

    @property
    def migration_label(self) -> str:
        return self.target_change_id

    @property
    def transition_label(self) -> str:
        return self.transition_job

    @property
    def publication_label(self) -> str:
        return self.publication_job

    @property
    def registry_stable_key(self) -> str:
        return f"release:{self.current_change_id}"

    @property
    def registry_prepare_key(self) -> str:
        return f"prepare:{self.target_change_id}"

    @property
    def registry_release_key(self) -> str:
        return f"release:{self.target_change_id}"

    @property
    def registry_compensation_key(self) -> str:
        return f"compensate:{self.registry_prepare_key}"

    @property
    def recovery_audit_key(self) -> str:
        return f"audit:recovery:{self.target_change_id}"

    @property
    def contract_configmaps(self) -> tuple[str, ...]:
        return (
            self.schema_contract,
            self.compatibility_contract,
            self.credential_contract,
            self.controller_contract,
            self.publication_contract,
            self.audit_contract,
        )

    @property
    def semantic_vector(self) -> tuple[str, ...]:
        """Facts that must change in addition to renaming an instance."""

        return (
            self.current_version,
            self.target_version,
            self.current_epoch,
            self.target_epoch,
            self.current_credential_generation,
            self.target_credential_generation,
            self.batch_id,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(
            self.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
    ) -> KubernetesInteractionInstanceSpec:
        expected = set(cls.__dataclass_fields__)
        supplied = set(payload)
        missing = sorted(expected - supplied)
        unexpected = sorted(supplied - expected)
        if missing or unexpected:
            raise ValueError(
                "invalid Kubernetes interaction instance fields: "
                f"missing={missing}, unexpected={unexpected}"
            )
        instance = cls(**{key: str(payload[key]) for key in expected})
        instance.validate()
        return instance

    @classmethod
    def from_path(
        cls,
        path: str | Path,
    ) -> KubernetesInteractionInstanceSpec:
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("instance specification must be a JSON object")
        return cls.from_dict(payload)

    def validate(self) -> None:
        blank = sorted(
            name
            for name, value in self.as_dict().items()
            if not str(value).strip()
        )
        if blank:
            raise ValueError(f"blank instance fields: {blank}")
        dns_fields = (
            "namespace",
            "application",
            "change_stem",
            "api_service",
            "current_api_deployment",
            "target_api_deployment",
            "current_worker_deployment",
            "target_worker_deployment",
            "current_credential",
            "next_credential",
            "backup_job",
            "transition_job",
            "publication_job",
            "service_account",
            "observer_role",
            "schema_contract",
            "compatibility_contract",
            "credential_contract",
            "controller_contract",
            "publication_contract",
            "audit_contract",
            "database_catalog",
            "compatibility_bridge",
            "batch_state",
            "change_record",
            "release_ledger",
            "recovery_audit",
        )
        invalid_dns = [
            name
            for name in dns_fields
            if len(getattr(self, name)) > 63
            or _DNS_LABEL.fullmatch(getattr(self, name)) is None
        ]
        if invalid_dns:
            raise ValueError(f"invalid DNS-label instance fields: {invalid_dns}")
        if (
            not self.migration_generate_name.endswith("-")
            or len(self.migration_generate_name) > 58
            or _DNS_LABEL.fullmatch(self.migration_generate_name[:-1]) is None
        ):
            raise ValueError("migration_generate_name must be a safe generateName prefix")
        label_values = (
            self.current_version,
            self.target_version,
            self.migration_label,
            self.transition_label,
            self.publication_label,
        )
        if any(
            len(value) > 63 or _LABEL_VALUE.fullmatch(value) is None
            for value in label_values
        ):
            raise ValueError("version and owner labels must be Kubernetes-safe")
        if self.current_version == self.target_version:
            raise ValueError("current and target versions must differ")
        try:
            current_epoch = int(self.current_epoch)
            target_epoch = int(self.target_epoch)
            current_generation = int(self.current_credential_generation)
            target_generation = int(self.target_credential_generation)
        except ValueError as error:
            raise ValueError("epoch and credential generations must be integers") from error
        if target_epoch <= current_epoch:
            raise ValueError("target_epoch must be greater than current_epoch")
        if target_generation <= current_generation:
            raise ValueError(
                "target_credential_generation must exceed the current generation"
            )
        workload_names = {
            self.api_service,
            self.current_api_deployment,
            self.target_api_deployment,
            self.current_worker_deployment,
            self.target_worker_deployment,
            self.current_credential,
            self.next_credential,
            self.backup_job,
            self.transition_job,
            self.publication_job,
            self.service_account,
            self.observer_role,
        }
        if len(workload_names) != 12:
            raise ValueError("native workload object names must be distinct")
        configmaps = {
            *self.contract_configmaps,
            self.database_catalog,
            self.compatibility_bridge,
            self.batch_state,
            self.change_record,
            self.release_ledger,
            self.recovery_audit,
        }
        if len(configmaps) != 12:
            raise ValueError("ConfigMap object names must be distinct")


DEFAULT_KUBERNETES_INTERACTION_INSTANCE = KubernetesInteractionInstanceSpec(
    scenario_id="k8s-constraint-interactions-dev-005",
    namespace="aftermath-interactions",
    application="orders",
    change_stem="orders-platform",
    current_version="v1",
    target_version="v2",
    current_epoch="1",
    target_epoch="2",
    current_credential_generation="1",
    target_credential_generation="2",
    batch_id="batch-4821",
    api_service="orders-api",
    current_api_deployment="orders-api-v1",
    target_api_deployment="orders-api-v2",
    current_worker_deployment="orders-worker-v1",
    target_worker_deployment="orders-worker-v2",
    current_credential="orders-db-current",
    next_credential="orders-db-next",
    backup_job="orders-backup-epoch1",
    migration_generate_name="orders-platform-migration-",
    transition_job="orders-worker-transition",
    publication_job="orders-release-publication",
    service_account="orders-runner",
    observer_role="orders-observer",
    schema_contract="schema-contract",
    compatibility_contract="compatibility-contract",
    credential_contract="credential-contract",
    controller_contract="controller-contract",
    publication_contract="publication-contract",
    audit_contract="audit-contract",
    database_catalog="database-catalog",
    compatibility_bridge="schema-compatibility-bridge",
    batch_state="worker-batch-state",
    change_record="change-record",
    release_ledger="release-ledger",
    recovery_audit="recovery-audit",
)
DEFAULT_KUBERNETES_INTERACTION_INSTANCE.validate()


def active_kubernetes_interaction_instance() -> KubernetesInteractionInstanceSpec:
    source = os.environ.get(INSTANCE_ENVIRONMENT_VARIABLE, "").strip()
    if not source:
        return DEFAULT_KUBERNETES_INTERACTION_INSTANCE
    return KubernetesInteractionInstanceSpec.from_path(source)


ACTIVE_KUBERNETES_INTERACTION_INSTANCE = active_kubernetes_interaction_instance()


_MATCHED_VARIANTS = (
    ("state_01", "no_primary_effect", "discard_failed_change"),
    (
        "state_02",
        "primary_effect_uncertain",
        "compensate_and_discard_failed_change",
    ),
    (
        "state_03",
        "downstream_effect_missing",
        "create_deferred_transition_owner",
    ),
    (
        "state_04",
        "downstream_effect_pending_or_accepted",
        "preserve_deferred_transition_owner",
    ),
    (
        "state_05",
        "downstream_effect_pending_or_accepted",
        "renew_bridge_and_preserve_transition_owner",
    ),
    (
        "state_06",
        "downstream_effect_pending_or_accepted",
        "resume_worker_transition",
    ),
    (
        "state_07",
        "downstream_effect_missing",
        "create_publication_owner",
    ),
    (
        "state_08",
        "downstream_effect_pending_or_accepted",
        "resume_publication_owner",
    ),
    (
        "state_09",
        "downstream_effect_missing",
        "reconcile_completed_publication",
    ),
    (
        "state_10",
        "downstream_effect_pending_or_accepted",
        "close_accepted_publication",
    ),
    (
        "state_11",
        "downstream_effect_missing",
        "repair_api_consumer_before_publication",
    ),
    (
        "state_12",
        "downstream_effect_missing",
        "create_worker_transition",
    ),
    (
        "state_13",
        "downstream_effect_missing",
        "rotate_shared_credential",
    ),
)


def kubernetes_interaction_blueprint(
    instance: KubernetesInteractionInstanceSpec,
    *,
    instance_id: str,
    benchmark_split: str,
    hidden_test_eligible: bool,
) -> dict[str, Any]:
    instance.validate()
    if not instance_id.strip():
        raise ValueError("instance_id must be non-empty")
    if benchmark_split not in {"development", "public_dev", "hidden_test"}:
        raise ValueError(f"unsupported benchmark split: {benchmark_split}")
    if hidden_test_eligible is not (benchmark_split == "hidden_test"):
        raise ValueError(
            "hidden_test_eligible must agree with benchmark_split"
        )
    return {
        "schema_version": "0.6-draft",
        "scenario_id": instance.scenario_id,
        "domain_id": "kubernetes",
        "instance_id": instance_id,
        "instance_spec_sha256": instance.sha256,
        "family": "k8s-constraint-interaction-recovery",
        "runtime_id": "kubernetes-v1.34",
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
            "instance-specific exact replay and hard admission pending"
        ),
        "title": (
            "Recover an interrupted two-consumer schema change by "
            "composing native constraints"
        ),
        "user_instruction": (
            f"Recover the interrupted {instance.application} platform "
            f"change from schema epoch {instance.current_epoch} to "
            f"{instance.target_epoch}. Leave both consumers, the database "
            "catalog, shared credentials, controller-owned work, release "
            "records and external registry in one valid state. Reconstruct "
            "what actually happened from authoritative Kubernetes objects, "
            "controller evidence and registry records. Apply every visible "
            "compatibility, ownership, publication and audit contract "
            "together. Preserve valid prior effects and immutable evidence, "
            "avoid duplicate external events, and verify the resulting "
            "cross-system state."
        ),
        "fixture": {
            "namespace": instance.namespace,
            "application": instance.application,
            "change": instance.target_change_id,
            "current_epoch": instance.current_epoch,
            "target_epoch": instance.target_epoch,
            "current_version": instance.current_version,
            "target_version": instance.target_version,
            "api_deployment": instance.target_api_deployment,
            "worker_deployment": instance.target_worker_deployment,
            "api_service": instance.api_service,
            "catalog_configmap": instance.database_catalog,
            "credential_secret": instance.current_credential,
            "bridge_configmap": instance.compatibility_bridge,
            "batch_configmap": instance.batch_state,
            "batch_id": instance.batch_id,
            "transition_controller": instance.transition_job,
            "publication_controller": instance.publication_job,
            "change_record_configmap": instance.change_record,
            "audit_configmap": instance.recovery_audit,
        },
        "ambiguous_operation": {
            "operation": (
                f"execute the approved {instance.application} schema "
                "migration and coordinated rollout"
            ),
            "surface_result": (
                "HTTP connection lost before the change orchestration "
                "response"
            ),
        },
        "matched_variants": [
            {
                "id": variant_id,
                "boundary_class_id": boundary_class_id,
                "recovery_signature_class": signature,
            }
            for variant_id, boundary_class_id, signature in _MATCHED_VARIANTS
        ],
        "required_semantic_recovery_directions": [
            signature for _variant, _boundary, signature in _MATCHED_VARIANTS
        ],
        "public_tool_policy": {
            "ordinary_kubernetes_object_reads": True,
            "pod_and_job_log_reads": True,
            "native_create_apply_patch_delete": True,
            "ordinary_registry_get_and_post": True,
            "global_state_summary": False,
            "recommended_action_tool": False,
            "hidden_variant_label": False,
        },
        "admission_profile": {
            "constraint_derived_scope": {
                "minimum_counterfactual_flips": 8,
                "require_projection_witnesses": True,
                "minimum_projection_witnesses": 10,
            }
        },
        "admission_status": "unvalidated",
    }


__all__ = [
    "ACTIVE_KUBERNETES_INTERACTION_INSTANCE",
    "DEFAULT_KUBERNETES_INTERACTION_INSTANCE",
    "INSTANCE_ENVIRONMENT_VARIABLE",
    "KubernetesInteractionInstanceSpec",
    "active_kubernetes_interaction_instance",
    "kubernetes_interaction_blueprint",
]
