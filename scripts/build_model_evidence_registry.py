from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.model_evidence_registry import (
    COMPONENTS,
    _canonical_sha256,
    _current_formal_identities,
    _load_artifact_condition,
    _load_local_condition,
    _sha256,
    _trajectory_set_sha256,
)
from aftermath_bench.schema import repository_root


ROOT = repository_root()


def _score(trajectories: list[dict[str, Any]]) -> dict[str, Any]:
    errors: dict[str, int] = {}
    for item in trajectories:
        if item["primary_error"]:
            error = str(item["primary_error"])
            errors[error] = errors.get(error, 0) + 1
    pass_count = sum(item["passed"] for item in trajectories)
    return {
        "completed_runs": len(trajectories),
        "task_pass_count": pass_count,
        "component_pass_counts": {
            name: sum(item["components"][name] is True for item in trajectories)
            for name in COMPONENTS
        },
        "matched_group_success": pass_count == len(trajectories),
        "error_attribution": errors,
    }


def _condition(
    *,
    condition_id: str,
    accounting_status: str,
    membership: str,
    scenario_id: str,
    scenario_path: str | None,
    domain_id: str,
    family_id: str,
    instance_id: str,
    model: str,
    provider: str,
    provider_service: str,
    repetition: int,
    source: dict[str, Any],
    evidence: dict[str, Any],
    formal_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seed = {
        "condition_id": condition_id,
        "accounting_status": accounting_status,
        "membership": membership,
        "scenario": {
            "scenario_id": scenario_id,
            "path": scenario_path,
            "domain_id": domain_id,
            "family_id": family_id,
            "instance_id": instance_id,
            "variant_ids": [],
        },
        "model": {
            "name": model,
            "provider": provider,
            "provider_service": provider_service,
            "repetition": repetition,
        },
        "source": source,
        "evidence": evidence,
    }
    if evidence["kind"] == "artifact-audit":
        observed = _load_artifact_condition(seed, ROOT)
    else:
        observed = _load_local_condition(seed, ROOT)
    trajectories = observed["trajectories"]
    seed["scenario"]["variant_ids"] = [
        item["variant_id"] for item in trajectories
    ]
    identity = formal_identity or {
        "scenario_sha256": (
            _sha256(ROOT / scenario_path) if scenario_path is not None else None
        ),
        "tool_contract_sha256": None,
        "evaluator_sha256": None,
        "formal_input_lock_sha256": None,
    }
    seed["identity"] = identity
    seed["identity_sha256"] = _canonical_sha256(identity)
    seed["summary_sha256"] = observed["summary_sha256"]
    seed["trajectory_set_sha256"] = _trajectory_set_sha256(trajectories)
    seed["infrastructure_valid"] = observed["infrastructure_valid"]
    seed["score"] = _score(trajectories)
    return seed


def _artifact_condition(
    *,
    evidence_id: str,
    audit_condition_id: str,
    accounting_status: str,
    membership: str,
    domain_id: str,
    family_id: str,
    instance_id: str,
) -> dict[str, Any]:
    base = f"data/evidence/model-runs/{evidence_id}"
    audit = json.loads((ROOT / base / "artifact-audit.json").read_text())
    selected = next(
        item
        for item in audit["conditions"]
        if item["condition_id"] == audit_condition_id
    )
    provenance = json.loads(
        (ROOT / base / "import-provenance.json").read_text()
    )
    return _condition(
        condition_id=f"{evidence_id}/{audit_condition_id}",
        accounting_status=accounting_status,
        membership=membership,
        scenario_id=audit["scenario_id"],
        scenario_path=audit["scenario"]["path"],
        domain_id=domain_id,
        family_id=family_id,
        instance_id=instance_id,
        model=selected["model"],
        provider=selected["provider"],
        provider_service=selected["provider_service"],
        repetition=selected["repetition"],
        source={
            "kind": "github-actions",
            "run_id": audit["source_run_id"],
            "condition": audit_condition_id,
            "artifact_name": provenance["artifact_name"],
            "artifact_digest": provenance["artifact_digest"],
            "artifact_id": provenance["artifact_id"],
            "artifact_size_in_bytes": provenance["artifact_size_in_bytes"],
            "head_sha": provenance["source_commit"],
            "workflow_path": provenance["source_workflow"],
        },
        evidence={
            "kind": "artifact-audit",
            "audit_path": f"{base}/artifact-audit.json",
            "audit_condition_id": audit_condition_id,
            "files_manifest_path": f"{base}/files.json",
            "files_manifest_sha256": _sha256(ROOT / base / "files.json"),
        },
    )


def build_registry() -> dict[str, Any]:
    conditions = [
        _condition(
            condition_id="github-runs-30865035666-30872359883/kubernetes-interaction/glm-5.2",
            accounting_status="ordinary-model-tested",
            membership="active-hard",
            scenario_id="k8s-constraint-interactions-dev-005",
            scenario_path="data/scenarios/k8s-constraint-interactions-dev-005/scenario.json",
            domain_id="kubernetes",
            family_id="k8s-constraint-interaction-recovery",
            instance_id="dev-005",
            model="glm-5.2",
            provider="openai-compatible",
            provider_service="bigmodel",
            repetition=1,
            source={
                "kind": "github-actions-coverage-assembly",
                "run_id": 30865035666,
                "supplemental_run_ids": [30872359883],
                "condition": "ordinary",
            },
            evidence={
                "kind": "local-summary",
                "summary_path": "data/evidence/kubernetes-interaction-ordinary-glm52-20260804/summary.json",
                "trajectory_root": "data/evidence/kubernetes-interaction-ordinary-glm52-20260804/repetition-01",
                "files_manifest_path": "data/evidence/kubernetes-interaction-ordinary-glm52-20260804/files.json",
                "files_manifest_sha256": _sha256(ROOT / "data/evidence/kubernetes-interaction-ordinary-glm52-20260804/files.json"),
            },
        ),
        _condition(
            condition_id="github-run-30881911583/erpnext-shared-batch/glm-5.2",
            accounting_status="ordinary-model-tested",
            membership="archived-hard-development",
            scenario_id="erpnext-shared-batch-recovery-dev-001",
            scenario_path=None,
            domain_id="erpnext",
            family_id="erpnext-shared-batch-corrective-recovery",
            instance_id="dev-001",
            model="glm-5.2",
            provider="openai-compatible",
            provider_service="bigmodel",
            repetition=1,
            source={
                "kind": "github-actions",
                "run_id": 30881911583,
                "condition": "ordinary",
                "head_sha": "60dfd65",
            },
            evidence={
                "kind": "local-summary",
                "summary_path": "data/evidence/erpnext-shared-batch-ordinary-glm52-20260804/summary.json",
                "trajectory_root": "data/evidence/erpnext-shared-batch-ordinary-glm52-20260804/repetition-01",
                "files_manifest_path": "data/evidence/erpnext-shared-batch-ordinary-glm52-20260804/files.json",
                "files_manifest_sha256": _sha256(ROOT / "data/evidence/erpnext-shared-batch-ordinary-glm52-20260804/files.json"),
            },
        ),
        _artifact_condition(
            evidence_id="github-run-30864156919-manufacturing-ordinary",
            audit_condition_id="glm-5.2",
            accounting_status="ordinary-model-tested",
            membership="active-hard",
            domain_id="erpnext",
            family_id="erpnext-manufacturing-rework",
            instance_id="dev-002",
        ),
        _artifact_condition(
            evidence_id="github-run-30858985560-package-r2-ordinary",
            audit_condition_id="glm-5.2",
            accounting_status="ordinary-model-tested",
            membership="active-hard",
            domain_id="forgejo",
            family_id="forgejo-package-provenance-recovery",
            instance_id="dev-001",
        ),
        _artifact_condition(
            evidence_id="github-run-30858985560-package-r2-ordinary",
            audit_condition_id="deepseek-v4-pro",
            accounting_status="ordinary-model-tested",
            membership="active-hard",
            domain_id="forgejo",
            family_id="forgejo-package-provenance-recovery",
            instance_id="dev-001",
        ),
        _artifact_condition(
            evidence_id="github-run-30985786988-package-r1-ordinary",
            audit_condition_id="glm-5.2",
            accounting_status="ordinary-model-tested",
            membership="active-hard",
            domain_id="forgejo",
            family_id="forgejo-package-provenance-recovery",
            instance_id="dev-001",
        ),
        _artifact_condition(
            evidence_id="github-run-30985786988-package-r1-ordinary",
            audit_condition_id="deepseek-v4-pro",
            accounting_status="ordinary-model-tested",
            membership="active-hard",
            domain_id="forgejo",
            family_id="forgejo-package-provenance-recovery",
            instance_id="dev-001",
        ),
        _condition(
            condition_id="github-run-30560679399/forgejo-publication/glm-5.2",
            accounting_status="historical-development",
            membership="historical-superseded-contract",
            scenario_id="forgejo-release-publication-dev-002",
            scenario_path="data/scenarios/forgejo-release-publication-dev-002/scenario.json",
            domain_id="forgejo",
            family_id="forgejo-release-package-publication",
            instance_id="dev-002",
            model="glm-5.2",
            provider="openai-compatible",
            provider_service="bigmodel",
            repetition=1,
            source={
                "kind": "github-actions",
                "run_id": 30560679399,
                "condition": "ordinary",
                "head_sha": "0d4840df92a887c125f0a4288e90b564b9aabc85",
            },
            evidence={
                "kind": "local-summary",
                "summary_path": "data/evidence/forgejo-publication-ordinary-final-20260731/model-runs/summary.json",
                "trajectory_root": "data/evidence/forgejo-publication-ordinary-final-20260731/model-runs/repetition-01",
            },
        ),
        _condition(
            condition_id="github-run-30519698310/erpnext-sales-return/glm-5.2",
            accounting_status="historical-development",
            membership="historical-superseded-instance",
            scenario_id="erpnext-sales-return-dev-001",
            scenario_path="data/scenarios/erpnext-sales-return-dev-001/scenario.json",
            domain_id="erpnext",
            family_id="erpnext-sales-return-exchange-reconciliation",
            instance_id="dev-001",
            model="glm-5.2",
            provider="openai-compatible",
            provider_service="bigmodel",
            repetition=1,
            source={
                "kind": "github-actions",
                "run_id": 30519698310,
                "condition": "ordinary",
                "head_sha": "9e2760a253c41351313f580de3c511cfac6125b3",
            },
            evidence={
                "kind": "local-summary",
                "summary_path": "data/evidence/erpnext-sales-return-ordinary-20260730/summary.json",
                "trajectory_root": "data/evidence/erpnext-sales-return-ordinary-20260730/repetition-01",
            },
        ),
    ]
    formal = _current_formal_identities(ROOT)
    controls = (
        (
            "erpnext-manufacturing-rework-public-dev-002",
            "erpnext",
            "erpnext-manufacturing-rework",
            "dev-002",
            "glm-5.2",
            "bigmodel",
        ),
        (
            "erpnext-sales-return-public-dev-001-r1",
            "erpnext",
            "erpnext-sales-return-exchange-reconciliation",
            "dev-001",
            "glm-5.2",
            "bigmodel",
        ),
        (
            "forgejo-release-publication-public-dev-002-r1",
            "forgejo",
            "forgejo-release-package-publication",
            "dev-002",
            "glm-5.2",
            "bigmodel",
        ),
        (
            "k8s-constraint-interactions-public-dev-006",
            "kubernetes",
            "k8s-constraint-interaction-recovery",
            "dev-006",
            "DeepSeek-V4-Pro",
            "paratera",
        ),
    )
    scenario_paths = {
        item["scenario_id"]: item["scenario_path"]
        for item in json.loads((ROOT / "data/release_manifest.json").read_text())[
            "scenario_bindings"
        ]
    }
    for scenario_id, domain, family, instance, model, service in controls:
        base = f"data/evidence/formal/aftermathbench-2026.08-r1/{domain}/{family}/{instance}"
        conditions.append(
            _condition(
                condition_id=f"formal-control/{domain}/{family}/{instance}",
                accounting_status="control-only",
                membership="current-formal",
                scenario_id=scenario_id,
                scenario_path=scenario_paths[scenario_id],
                domain_id=domain,
                family_id=family,
                instance_id=instance,
                model=model,
                provider="openai-compatible",
                provider_service=service,
                repetition=1,
                source={
                    "kind": "formal-execution-control",
                    "run_id": None,
                    "condition": "execution-control",
                    "benchmark_release_id": "aftermathbench-2026.08-r1",
                },
                evidence={
                    "kind": "formal-control",
                    "summary_path": f"{base}/completion/roles/execution_control/support/summary.json",
                    "trajectory_root": f"{base}/completion/roles/raw_run_archive/support/trajectories",
                },
                formal_identity=formal[scenario_id],
            )
        )
    return {
        "schema_version": "1.0",
        "benchmark_release_id": "aftermathbench-2026.08-r1",
        "conditions": conditions,
        "quarantined_imports": [
            {
                "quarantine_id": "github-run-30985603153-forgejo-migration",
                "source_run_id": 30985603153,
                "head_branch": "forgejo-migration-model-rerun-20260805",
                "head_sha": "ff247340b0d5b757ad9028649b9b466bc823c1d4",
                "workflow_name": "forgejo-migration-public-development-model",
                "workflow_status": "completed",
                "workflow_conclusion": "success",
                "artifact_name": "forgejo-migration-public-dev-model-30985603153",
                "artifact_digest": "sha256:ce42a6ebd5c5ad55e792052f5ad7909afc8d4f8dfa749ad24d6177c24725be55",
                "artifact_size_bytes": 771020,
                "trajectory_structure_valid": True,
                "secret_hits": [],
                "quarantine_reason": "restore archives are prohibited from public evidence imports",
                "prohibited_paths": [
                    "dispatch_request_not_reached-bundle/forgejo-data.tar.gz",
                    "migration_applied_workflow_failed-bundle/forgejo-data.tar.gz",
                    "workflow_completed_dispatch_response_lost-bundle/forgejo-data.tar.gz",
                    "workflow_queued_runner_unavailable-bundle/forgejo-data.tar.gz",
                ],
                "counted_as_model_evidence": False,
                "score_status": "not_imported",
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the canonical model-evidence registry."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "model_evidence_registry.json",
    )
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(build_registry(), indent=2, sort_keys=True, ensure_ascii=True)
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
