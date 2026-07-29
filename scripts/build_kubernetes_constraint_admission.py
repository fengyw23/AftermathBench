from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.kubernetes_constraint_faults import (
    KUBERNETES_CONSTRAINT_VARIANTS,
)
from aftermath_bench.integrations.kubernetes_constraint_prefix import SCENARIO_ID
from aftermath_bench.integrations.kubernetes_settlement_recovery import (
    _complete,
    _find,
)
from aftermath_bench.kubernetes_constraint_prompt_audit import (
    build_constraint_prompt_audit,
)
from aftermath_bench.native_admission import validate_native_scenario
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _external(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["key"]): item for item in state["external_deliveries"]}


def _compact_capture(report: dict[str, Any]) -> dict[str, Any]:
    state = report["final_evidence"]
    boundary = state["boundary_facts"]
    expected_scope = report["semantic_recovery_direction"]
    epoch_two = expected_scope in {
        "publish_committed_cutover",
        "close_already_published_cutover",
    }
    configmaps = state["configmaps"]
    deployments = state["deployments"]
    service = _find(state["services"], "orders") or {}
    stable = _find(deployments, "orders-v1") or {}
    candidate = _find(deployments, "orders-v2") or {}
    catalog = _find(configmaps, "database-catalog") or {}
    ledger = _find(configmaps, "release-ledger") or {}
    audit = _find(configmaps, "recovery-audit") or {}
    change = _find(configmaps, "change-record") or {}
    backup = _find(state["jobs"], "orders-backup-epoch1") or {}
    migration_jobs = [
        item
        for item in state["jobs"]
        if item.get("metadata", {}).get("labels", {}).get("migration") == "orders-v2"
    ]
    migration = migration_jobs[0] if len(migration_jobs) == 1 else {}
    deliveries = _external(state)
    expected_epoch = "2" if epoch_two else "1"
    expected_version = "v2" if epoch_two else "v1"
    return {
        "boundary": boundary,
        "expected": {
            "scope": expected_scope,
            "epoch": expected_epoch,
            "version": expected_version,
            "candidate_present": epoch_two,
            "release_present": epoch_two,
            "compensation_present": (
                expected_scope == "compensate_then_discard_candidate"
            ),
        },
        "contracts": {
            name: (_find(configmaps, name) or {}).get("data", {}) == data
            for name, data in boundary.get("contract_data", {}).items()
        },
        "catalog": {
            "epoch": catalog.get("data", {}).get("schemaEpoch"),
            "preserved": catalog.get("data", {}) == boundary.get("catalog_data"),
        },
        "migration": {
            "count": len(migration_jobs),
            "uid": migration.get("metadata", {}).get("uid", ""),
            "preserved": (
                len(migration_jobs) == boundary.get("migration_job_count")
                and str(migration.get("metadata", {}).get("uid", ""))
                == boundary.get("migration_job_uid")
            ),
        },
        "serving": {
            "version": service.get("spec", {}).get("selector", {}).get("version"),
            "stable_replicas": stable.get("spec", {}).get("replicas"),
            "candidate_present": bool(candidate),
            "candidate_available": bool(candidate) and _complete_deployment(candidate),
        },
        "closure": {
            "change_resolved": change.get("data", {}).get("orders-v2.state")
            == "resolved",
            "ledger_closed": ledger.get("data", {}).get("orders-v2.status") == "closed",
            "audit_complete": audit.get("data", {}).get("orders-v2.status")
            == "complete",
        },
        "external": {
            "stable_present": "release:orders-v1" in deliveries,
            "prepare_present": "prepare:orders-v2" in deliveries,
            "compensation_present": "compensate:prepare:orders-v2" in deliveries,
            "release_present": "release:orders-v2" in deliveries,
            "closure_present": "audit:recovery:orders-v2" in deliveries,
            "all_exactly_once": all(
                item.get("attempt_count") == 1 for item in deliveries.values()
            ),
        },
        "preservation": {
            "backup_complete": bool(backup) and _complete(backup),
            "backup_uid": str(backup.get("metadata", {}).get("uid", ""))
            == boundary.get("backup_job_uid"),
            "stable_uid": str(stable.get("metadata", {}).get("uid", ""))
            == boundary.get("stable_deployment_uid"),
            "rbac": all(
                str(
                    (_find(state[resource], name) or {})
                    .get("metadata", {})
                    .get("uid", "")
                )
                == boundary.get(key)
                for resource, name, key in (
                    ("serviceaccounts", "orders-runner", "service_account_uid"),
                    ("roles", "orders-observer", "role_uid"),
                    ("rolebindings", "orders-observer", "rolebinding_uid"),
                )
            ),
            "nightly": str(
                (_find(state["cronjobs"], "nightly-report") or {})
                .get("metadata", {})
                .get("uid", "")
            )
            == boundary.get("nightly_report_uid"),
        },
    }


def _complete_deployment(document: dict[str, Any]) -> bool:
    desired = int(document.get("spec", {}).get("replicas", 0))
    return (
        desired > 0
        and int(document.get("status", {}).get("availableReplicas", 0)) >= desired
    )


def _equals(selector: str, expected: Any) -> dict[str, Any]:
    return {"selector": selector, "operator": "any_equals", "expected": expected}


def _intersects(left: str, right: str) -> dict[str, Any]:
    return {"selector": left, "operator": "intersects", "other_selector": right}


def _relation(
    source: str, target: str, relation_type: str, *clauses: dict[str, Any]
) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "type": relation_type,
        "evidence": "native replay projection",
        "replay": list(clauses),
    }


def _observed_graph() -> dict[str, Any]:
    entities = (
        ("authorization", "ConfigMap"),
        ("schema_contract", "ConfigMap"),
        ("serving_contract", "ConfigMap"),
        ("registry_contract", "ConfigMap"),
        ("audit_contract", "ConfigMap"),
        ("catalog", "ConfigMap"),
        ("migration_job", "Job"),
        ("migration_pod", "Pod"),
        ("stable_deployment", "Deployment"),
        ("candidate_deployment", "Deployment"),
        ("service", "Service"),
        ("stable_secret", "Secret"),
        ("candidate_secret", "Secret"),
        ("backup_job", "Job"),
        ("service_account", "ServiceAccount"),
        ("role", "Role"),
        ("rolebinding", "RoleBinding"),
        ("nightly_report", "CronJob"),
        ("stable_registry", "ExternalEvent"),
        ("prepare_registry", "ExternalEvent"),
        ("compensation_registry", "ExternalEvent"),
        ("release_registry", "ExternalEvent"),
        ("change_record", "ConfigMapEntry"),
        ("release_ledger", "ConfigMapEntry"),
        ("recovery_audit", "ConfigMapEntry"),
        ("closure_registry", "ExternalEvent"),
    )
    relations = (
        _relation(
            "authorization",
            "catalog",
            "constrains_mutation",
            _equals("contracts.recovery-policy", True),
        ),
        _relation(
            "schema_contract",
            "catalog",
            "requires_monotonic_epoch",
            _equals("contracts.schema-contract", True),
            _intersects("catalog.epoch", "expected.epoch"),
        ),
        _relation(
            "catalog",
            "migration_job",
            "attested_by",
            _equals("migration.preserved", True),
        ),
        _relation(
            "migration_job",
            "migration_pod",
            "owns_execution_evidence",
            _equals("migration.count", 1),
        ),
        _relation(
            "migration_pod",
            "candidate_deployment",
            "determines_candidate_lifecycle",
            _intersects("serving.candidate_present", "expected.candidate_present"),
        ),
        _relation(
            "serving_contract",
            "service",
            "constrains_route",
            _equals("contracts.serving-contract", True),
            _intersects("serving.version", "expected.version"),
        ),
        _relation(
            "schema_contract",
            "service",
            "requires_compatible_epoch",
            _intersects("catalog.epoch", "expected.epoch"),
        ),
        _relation(
            "candidate_secret",
            "candidate_deployment",
            "credentials_for",
            _intersects("serving.candidate_present", "expected.candidate_present"),
        ),
        _relation(
            "service_account",
            "candidate_deployment",
            "executes",
            _equals("preservation.rbac", True),
        ),
        _relation(
            "role", "rolebinding", "bound_by", _equals("preservation.rbac", True)
        ),
        _relation(
            "rolebinding",
            "service_account",
            "binds",
            _equals("preservation.rbac", True),
        ),
        _relation(
            "stable_secret",
            "stable_deployment",
            "credentials_for",
            _equals("preservation.stable_uid", True),
        ),
        _relation(
            "backup_job",
            "catalog",
            "guards_schema",
            _equals("preservation.backup_complete", True),
            _equals("preservation.backup_uid", True),
        ),
        _relation(
            "backup_job",
            "migration_job",
            "precedes",
            _equals("preservation.backup_uid", True),
        ),
        _relation(
            "registry_contract",
            "prepare_registry",
            "governs_preparation",
            _equals("contracts.registry-contract", True),
        ),
        _relation(
            "prepare_registry",
            "compensation_registry",
            "may_require_compensation",
            _intersects(
                "external.compensation_present", "expected.compensation_present"
            ),
        ),
        _relation(
            "service",
            "release_registry",
            "permits_publication",
            _intersects("external.release_present", "expected.release_present"),
        ),
        _relation(
            "registry_contract",
            "release_registry",
            "guards_publication",
            _equals("contracts.registry-contract", True),
        ),
        _relation(
            "stable_registry",
            "release_ledger",
            "preserves_prior_release",
            _equals("external.stable_present", True),
        ),
        _relation(
            "release_registry",
            "release_ledger",
            "closes_release",
            _equals("closure.ledger_closed", True),
        ),
        _relation(
            "authorization",
            "change_record",
            "closes_change",
            _equals("closure.change_resolved", True),
        ),
        _relation(
            "audit_contract",
            "recovery_audit",
            "defines_audit",
            _equals("contracts.audit-contract", True),
            _equals("closure.audit_complete", True),
        ),
        _relation(
            "release_ledger",
            "recovery_audit",
            "reconciled_by",
            _equals("closure.ledger_closed", True),
        ),
        _relation(
            "recovery_audit",
            "closure_registry",
            "emits_closure",
            _equals("external.closure_present", True),
            _equals("external.all_exactly_once", True),
        ),
        _relation(
            "nightly_report",
            "recovery_audit",
            "coexists_with",
            _equals("preservation.nightly", True),
        ),
        _relation(
            "schema_contract",
            "recovery_audit",
            "records_epoch",
            _equals("catalog.preserved", True),
        ),
    )
    return {
        "schema_version": "1.0",
        "scenario_id": SCENARIO_ID,
        "source": "native Kubernetes and registry replay with constraint-derived scope",
        "entities": [{"id": key, "type": kind} for key, kind in entities],
        "relations": list(relations),
        "protected_effects": [
            "authorization",
            "schema_contract",
            "serving_contract",
            "registry_contract",
            "audit_contract",
            "catalog",
            "backup_job",
            "stable_deployment",
        ],
        "required_evidence_groups": [
            ["authorization", "schema_contract", "catalog"],
            ["migration_job", "migration_pod", "backup_job"],
            ["stable_deployment", "candidate_deployment", "service"],
            ["prepare_registry", "release_registry", "closure_registry"],
            ["change_record", "release_ledger", "recovery_audit"],
        ],
        "evidence_tool_groups": [
            {
                "id": "constraints",
                "calls": [
                    {"tool": "list_objects", "arguments": {"resource": "configmaps"}}
                ],
            },
            {
                "id": "deployments",
                "calls": [
                    {"tool": "list_objects", "arguments": {"resource": "deployments"}}
                ],
            },
            {
                "id": "routing",
                "calls": [
                    {"tool": "list_objects", "arguments": {"resource": "services"}}
                ],
            },
            {
                "id": "jobs",
                "calls": [{"tool": "list_objects", "arguments": {"resource": "jobs"}}],
            },
            {"id": "events", "calls": [{"tool": "list_events", "arguments": {}}]},
            {
                "id": "external",
                "calls": [{"tool": "list_external_deliveries", "arguments": {}}],
            },
        ],
        "minimum_boundary_query_groups": 5,
        "single_query_decisive": False,
        "minimum_semantic_recovery_directions": 4,
        "action_branches": [
            {"id": "candidate_lifecycle", "mutation_tools": ["delete_object"]},
            {"id": "native_closure", "mutation_tools": ["patch_object"]},
            {"id": "external_obligations", "mutation_tools": ["post_external_event"]},
        ],
        "unsafe_actions": [
            "modify the committed database catalog",
            "delete migration or backup evidence",
            "repeat an accepted external event",
            "discard candidate resources after epoch 2 committed",
            "leave an escaped preparation event unresolved",
            "publish release before catalog and serving state agree",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    run_root = args.run_directory.resolve()
    runtime = run_root / "runtime"
    output = args.output_directory.resolve()
    artifacts = output / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    reports = [
        _read(runtime / f"{variant}-reference.json")
        for variant in KUBERNETES_CONSTRAINT_VARIANTS
    ]
    boundaries = {
        variant: _read(runtime / f"{variant}-boundary.json")
        for variant in KUBERNETES_CONSTRAINT_VARIANTS
    }
    reference = {
        "schema_version": "1.0",
        "scenario_id": SCENARIO_ID,
        "reports": [
            {
                "variant": report["variant"],
                "passed": report["evaluation"]["passed"],
                "query_tools": report["query_tools"],
                "query_events": [
                    {"tool": event["tool"], "arguments": event.get("arguments", {})}
                    for event in report["reference_trace"]
                    if event["tool"] not in report["mutation_tools"]
                ],
                "mutation_tools": report["mutation_tools"],
                "downstream_repairs": report["downstream_repairs"],
                "semantic_recovery_direction": report["semantic_recovery_direction"],
            }
            for report in reports
        ],
    }
    replay = {
        "schema_version": "1.0",
        "scenario_id": SCENARIO_ID,
        "captures": [
            {"variant": report["variant"], "evidence": _compact_capture(report)}
            for report in reports
        ],
    }
    blueprint_path = (
        repository_root()
        / "data"
        / "scenario_blueprints"
        / SCENARIO_ID
        / "scenario.json"
    )
    blueprint = _read(blueprint_path)
    prompt_audit = build_constraint_prompt_audit(
        load_native_scenario(blueprint_path),
        variant_facts={
            variant: report["counterfactual_facts"]
            for variant, report in boundaries.items()
        },
        prefix_trace=_read(runtime / "prefix.json").get("trace", []),
        visible_failure=next(iter(boundaries.values()))["visible_failure"],
    )
    _write(artifacts / "reference.json", reference)
    _write(artifacts / "observed_graph.json", _observed_graph())
    _write(artifacts / "replay_evidence.json", replay)
    _write(artifacts / "prompt_audit.json", prompt_audit)
    shutil.copyfile(runtime / "prefix.json", artifacts / "prefix.json")
    shutil.copyfile(
        run_root / "baselines" / "summary.json", artifacts / "baselines.json"
    )
    scenario = {
        **blueprint,
        "schema_version": "1.0",
        "benchmark_tier": "hard",
        "implementation_status": "native replay admitted",
        "admission_status": "validated",
        "admission_artifacts": {
            "admission": "artifacts/admission.json",
            "prefix": "artifacts/prefix.json",
            "reference": "artifacts/reference.json",
            "observed_graph": "artifacts/observed_graph.json",
            "baselines": "artifacts/baselines.json",
            "replay_evidence": "artifacts/replay_evidence.json",
            "prompt_audit": "artifacts/prompt_audit.json",
        },
    }
    _write(output / "scenario.json", scenario)
    report = validate_native_scenario(load_native_scenario(output / "scenario.json"))
    result = {
        "scenario_id": report.scenario_id,
        "requested_tier": report.requested_tier,
        "admitted_tier": report.admitted_tier,
        "passed": report.passed,
        "checks": report.checks,
        "observed": report.observed,
        "failures": list(report.failures),
        "artifact_sha256": report.artifact_sha256,
    }
    _write(artifacts / "admission.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if report.passed and report.admitted_tier == "hard" else 1


if __name__ == "__main__":
    raise SystemExit(main())
