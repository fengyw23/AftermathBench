from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.kubernetes_migration_faults import (
    KUBERNETES_MIGRATION_VARIANTS,
)
from aftermath_bench.integrations.kubernetes_migration_prefix import SCENARIO_ID
from aftermath_bench.integrations.kubernetes_migration_recovery import _complete
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


def _named(items: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(
        (
            item
            for item in items
            if item.get("metadata", {}).get("name") == name or item.get("key") == name
        ),
        {},
    )


def _compact_capture(report: dict[str, Any]) -> dict[str, Any]:
    state = report["final_evidence"]
    boundary = state["boundary_facts"]
    direction = report["semantic_recovery_direction"]
    configmaps = state["configmaps"]
    deployments = state["deployments"]
    jobs = state["jobs"]
    deliveries = state["external_deliveries"]
    policy = _named(configmaps, "recovery-policy").get("data", {})
    catalog = _named(configmaps, "database-catalog").get("data", {})
    ledger = _named(configmaps, "release-ledger").get("data", {})
    audit = _named(configmaps, "recovery-audit").get("data", {})
    stable = _named(deployments, "orders-v1")
    candidate = _named(deployments, "orders-v2")
    service = _named(state["services"], "orders")
    backup = _named(jobs, "orders-backup-epoch1")
    migration_jobs = [
        item
        for item in jobs
        if item.get("metadata", {}).get("labels", {}).get("migration") == "orders-v2"
    ]
    migration = migration_jobs[0] if len(migration_jobs) == 1 else {}
    external = {str(item["key"]): item for item in deliveries}
    epoch_two = direction in {"forward_complete", "repair_downstream_only"}
    compensation_required = direction == "compensate_external_effect"
    release_required = epoch_two
    expected_status = {
        "rollback_to_stable": "aborted",
        "compensate_external_effect": "compensated",
        "forward_complete": "active",
        "repair_downstream_only": "active",
    }[direction]
    recovery = external.get("audit:recovery:orders-v2", {})
    return {
        "policy": {
            "actions": [
                policy.get("epoch1Action"),
                policy.get("epoch1WithEscapedPreparationAction"),
                policy.get("epoch2BeforeCutoverAction"),
                policy.get("epoch2AfterPublishedCutoverAction"),
            ],
            "down_migration_allowed": policy.get("downMigrationAllowed"),
        },
        "boundary": boundary,
        "catalog": {
            "schema_epoch": catalog.get("schemaEpoch"),
            "history": catalog.get("history"),
        },
        "migration": {
            "count": len(migration_jobs),
            "uid": migration.get("metadata", {}).get("uid", ""),
            "complete": bool(migration) and _complete(migration),
            "failed": bool(migration)
            and int(migration.get("status", {}).get("failed", 0)) == 1,
        },
        "deployments": {
            "stable_uid": stable.get("metadata", {}).get("uid"),
            "stable_replicas": stable.get("spec", {}).get("replicas"),
            "candidate_present": bool(candidate),
            "candidate_replicas": candidate.get("spec", {}).get("replicas", 0),
            "candidate_available": (
                int(candidate.get("status", {}).get("availableReplicas", 0))
                >= int(candidate.get("spec", {}).get("replicas", 0))
                if candidate
                else False
            ),
        },
        "service": {
            "version": service.get("spec", {}).get("selector", {}).get("version")
        },
        "expected": {
            "direction": direction,
            "schema_epoch": "2" if epoch_two else "1",
            "serving_version": "v2" if epoch_two else "v1",
            "candidate_present": epoch_two,
            "ledger_status": expected_status,
            "compensation_required": compensation_required,
            "release_required": release_required,
        },
        "ledger": {"status": ledger.get("orders-v2.status")},
        "audit": {
            "status": audit.get("orders-v2.status"),
            "direction": audit.get("orders-v2.direction"),
            "migration_job_uid": audit.get("orders-v2.migration_job_uid"),
        },
        "external": {
            "stable_present": "release:orders-v1" in external,
            "prepare_present": "prepare:orders-v2" in external,
            "compensation_present": "compensate:prepare:orders-v2" in external,
            "release_present": "release:orders-v2" in external,
            "recovery_direction": recovery.get("payload", {}).get("direction"),
            "attempt_counts": [item.get("attempt_count") for item in deliveries],
        },
        "preservation": {
            "backup_complete": bool(backup) and _complete(backup),
            "backup_uid_matches": str(backup.get("metadata", {}).get("uid", ""))
            == boundary.get("backup_job_uid"),
            "stable_uid_matches": str(stable.get("metadata", {}).get("uid", ""))
            == boundary.get("stable_deployment_uid"),
            "policy_matches": policy == boundary.get("policy_data"),
            "catalog_matches": catalog == boundary.get("catalog_data"),
            "rbac_preserved": all(
                _named(state[key], name)
                for key, name in (
                    ("serviceaccounts", "orders-runner"),
                    ("roles", "orders-observer"),
                    ("rolebindings", "orders-observer"),
                )
            ),
            "nightly_preserved": bool(_named(state["cronjobs"], "nightly-report")),
        },
    }


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
        ("policy", "ConfigMap"),
        ("boundary", "FailureBoundary"),
        ("catalog", "ConfigMap"),
        ("migration_job", "Job"),
        ("migration_pod", "Pod"),
        ("candidate_deployment", "Deployment"),
        ("stable_deployment", "Deployment"),
        ("service", "Service"),
        ("candidate_secret", "Secret"),
        ("stable_secret", "Secret"),
        ("service_account", "ServiceAccount"),
        ("role", "Role"),
        ("rolebinding", "RoleBinding"),
        ("backup_job", "Job"),
        ("nightly_report", "CronJob"),
        ("stable_registry", "ExternalEvent"),
        ("prepare_registry", "ExternalEvent"),
        ("compensation_registry", "ExternalEvent"),
        ("release_registry", "ExternalEvent"),
        ("release_ledger", "ConfigMapEntry"),
        ("recovery_audit", "ConfigMapEntry"),
        ("recovery_registry", "ExternalEvent"),
    )
    relations = (
        _relation(
            "policy",
            "boundary",
            "selects_recovery_direction",
            _intersects("policy.actions.*", "expected.direction"),
        ),
        _relation(
            "policy",
            "catalog",
            "forbids_down_migration",
            _equals("policy.down_migration_allowed", "false"),
            _equals("preservation.policy_matches", True),
        ),
        _relation(
            "policy",
            "recovery_audit",
            "requires_audit_closure",
            _equals("audit.status", "complete"),
        ),
        _relation(
            "boundary",
            "catalog",
            "observes_schema_epoch",
            _intersects("boundary.schema_epoch", "catalog.schema_epoch"),
        ),
        _relation(
            "catalog",
            "migration_job",
            "constrains_migration_evidence",
            _intersects("boundary.migration_job_uid", "migration.uid"),
        ),
        _relation(
            "migration_job",
            "migration_pod",
            "owns_execution_evidence",
            _intersects("boundary.migration_job_count", "migration.count"),
        ),
        _relation(
            "migration_pod",
            "candidate_deployment",
            "determines_candidate_viability",
            _intersects("deployments.candidate_present", "expected.candidate_present"),
        ),
        _relation(
            "candidate_secret",
            "candidate_deployment",
            "credentials_for",
            _intersects("deployments.candidate_present", "expected.candidate_present"),
        ),
        _relation(
            "service_account",
            "candidate_deployment",
            "executes",
            _equals("preservation.rbac_preserved", True),
        ),
        _relation(
            "role",
            "rolebinding",
            "bound_by",
            _equals("preservation.rbac_preserved", True),
        ),
        _relation(
            "rolebinding",
            "service_account",
            "binds",
            _equals("preservation.rbac_preserved", True),
        ),
        _relation(
            "candidate_deployment",
            "service",
            "serves_candidate_when_required",
            _intersects("service.version", "expected.serving_version"),
        ),
        _relation(
            "stable_deployment",
            "service",
            "preserves_or_retires_stable_capacity",
            _equals("preservation.stable_uid_matches", True),
        ),
        _relation(
            "stable_secret",
            "stable_deployment",
            "credentials_for",
            _equals("preservation.stable_uid_matches", True),
        ),
        _relation(
            "service",
            "release_registry",
            "publishes_committed_cutover",
            _intersects("external.release_present", "expected.release_required"),
        ),
        _relation(
            "prepare_registry",
            "compensation_registry",
            "requires_compensation_when_escaped",
            _intersects(
                "external.compensation_present", "expected.compensation_required"
            ),
        ),
        _relation(
            "release_registry",
            "release_ledger",
            "closes_release_record",
            _intersects("ledger.status", "expected.ledger_status"),
        ),
        _relation(
            "compensation_registry",
            "release_ledger",
            "closes_compensated_record",
            _intersects("ledger.status", "expected.ledger_status"),
        ),
        _relation(
            "release_ledger",
            "recovery_audit",
            "attested_by",
            _intersects("audit.direction", "expected.direction"),
        ),
        _relation(
            "recovery_audit",
            "recovery_registry",
            "emits_exactly_once",
            _intersects("audit.direction", "external.recovery_direction"),
            {
                "selector": "external.attempt_counts.*",
                "operator": "all_equal",
                "expected": 1,
            },
        ),
        _relation(
            "stable_registry",
            "release_ledger",
            "preserves_stable_history",
            _equals("external.stable_present", True),
        ),
        _relation(
            "backup_job",
            "catalog",
            "guards_schema_recovery",
            _equals("preservation.backup_complete", True),
            _equals("preservation.backup_uid_matches", True),
        ),
        _relation(
            "backup_job",
            "migration_job",
            "precedes_migration",
            _equals("preservation.backup_complete", True),
        ),
        _relation(
            "backup_job",
            "recovery_audit",
            "retained_as_evidence",
            _equals("preservation.backup_uid_matches", True),
        ),
        _relation(
            "nightly_report",
            "recovery_audit",
            "coexists_with_recovery",
            _equals("preservation.nightly_preserved", True),
        ),
        _relation(
            "catalog",
            "recovery_audit",
            "preserves_immutable_history",
            _equals("preservation.catalog_matches", True),
        ),
    )
    return {
        "schema_version": "1.0",
        "scenario_id": SCENARIO_ID,
        "source": "native Kubernetes and registry replay with executable assertions",
        "entities": [{"id": key, "type": kind} for key, kind in entities],
        "relations": list(relations),
        "protected_effects": ["policy", "catalog", "backup_job", "stable_deployment"],
        "required_evidence_groups": [
            ["policy", "catalog"],
            ["migration_job", "migration_pod"],
            ["candidate_deployment", "stable_deployment", "service"],
            ["prepare_registry", "release_registry", "recovery_registry"],
        ],
        "evidence_tool_groups": [
            {
                "id": "policy_catalog",
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
                    {"tool": "list_objects", "arguments": {"resource": "services"}},
                    {"tool": "get_object", "arguments": {"resource": "service"}},
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
        "minimum_boundary_query_groups": 4,
        "single_query_decisive": False,
        "minimum_semantic_recovery_directions": 4,
        "action_branches": [
            {"id": "resource_scope", "mutation_tools": ["delete_object"]},
            {
                "id": "native_closure",
                "mutation_tools": ["patch_object", "apply_object"],
            },
            {"id": "external_effects", "mutation_tools": ["post_external_event"]},
        ],
        "unsafe_actions": [
            "down-migrate an already committed schema",
            "delete immutable migration or backup evidence",
            "repeat an already accepted external event",
            "roll back a committed cutover instead of completing records",
            "forward-complete a failed pre-commit migration",
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
        for variant in KUBERNETES_MIGRATION_VARIANTS
    ]
    reference = {
        "schema_version": "1.0",
        "scenario_id": SCENARIO_ID,
        "reports": [
            {
                "variant": report["variant"],
                "passed": report["evaluation"]["passed"],
                "query_tools": report["query_tools"],
                "query_events": [
                    {
                        "tool": event["tool"],
                        "arguments": event.get("arguments", {}),
                    }
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
    _write(artifacts / "reference.json", reference)
    _write(artifacts / "observed_graph.json", _observed_graph())
    _write(artifacts / "replay_evidence.json", replay)
    shutil.copyfile(runtime / "prefix.json", artifacts / "prefix.json")
    shutil.copyfile(
        run_root / "baselines" / "summary.json", artifacts / "baselines.json"
    )
    shutil.copyfile(runtime / "replay-audit.json", artifacts / "replay-audit.json")
    blueprint = _read(
        repository_root()
        / "data"
        / "scenario_blueprints"
        / SCENARIO_ID
        / "scenario.json"
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
