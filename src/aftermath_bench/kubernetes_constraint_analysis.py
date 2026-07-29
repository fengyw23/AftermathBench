from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .integrations.kubernetes_constraint_prefix import (
    RECOVERY_AUDIT_KEY,
    REGISTRY_COMPENSATION_KEY,
    REGISTRY_RELEASE_KEY,
)
from .integrations.kubernetes_constraint_recovery import (
    KubernetesConstraintEnvironment,
)


CONTRACT_NAMES = frozenset(
    {
        "recovery-policy",
        "schema-contract",
        "serving-contract",
        "registry-contract",
        "audit-contract",
    }
)
CLOSURE_RECORD_NAMES = frozenset(
    {"change-record", "release-ledger", "recovery-audit"}
)


def _resource(call: dict[str, Any]) -> str:
    return str(call.get("arguments", {}).get("resource", "")).lower().rstrip("s")


def _name(call: dict[str, Any]) -> str:
    return str(call.get("arguments", {}).get("name", ""))


def _query_facets(calls: Iterable[dict[str, Any]]) -> dict[str, bool]:
    calls = tuple(calls)
    listed_configmaps = any(
        call.get("name") == "list_objects" and _resource(call) == "configmap"
        for call in calls
    )
    fetched_names = {
        _name(call)
        for call in calls
        if call.get("name") == "get_object" and _resource(call) == "configmap"
    }
    listed_resources = {
        _resource(call)
        for call in calls
        if call.get("name") == "list_objects"
    }
    fetched_resources = {
        _resource(call)
        for call in calls
        if call.get("name") == "get_object"
    }
    return {
        "all_contracts": listed_configmaps or CONTRACT_NAMES <= fetched_names,
        "catalog": listed_configmaps or "database-catalog" in fetched_names,
        "migration_jobs": "job" in listed_resources or "job" in fetched_resources,
        "deployments": (
            "deployment" in listed_resources or "deployment" in fetched_resources
        ),
        "candidate_secret": (
            "secret" in listed_resources or "secret" in fetched_resources
        ),
        "service": "service" in listed_resources or "service" in fetched_resources,
        "external_registry": any(
            call.get("name") == "list_external_deliveries" for call in calls
        ),
        "closure_records": listed_configmaps or CLOSURE_RECORD_NAMES <= fetched_names,
    }


def _flatten(turns: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [call for turn in turns for call in turn.get("tool_calls", ())]


def _mutation_signature(call: dict[str, Any]) -> str:
    arguments = call.get("arguments", {})
    target = (
        arguments.get("idempotency_key")
        or arguments.get("name")
        or arguments.get("resource")
        or ""
    )
    return f"{call.get('name')}:{target}"


def analyze_kubernetes_constraint_report(report: dict[str, Any]) -> dict[str, Any]:
    turns = tuple(report.get("turns", ()))
    mutation_tools = set(KubernetesConstraintEnvironment.MUTATION_TOOLS)
    mutation_turns = [
        index
        for index, turn in enumerate(turns)
        if any(call.get("name") in mutation_tools for call in turn.get("tool_calls", ()))
    ]
    first_mutation_turn = min(mutation_turns) if mutation_turns else len(turns)
    last_mutation_turn = max(mutation_turns) if mutation_turns else -1
    before_calls = _flatten(turns[:first_mutation_turn])
    after_calls = _flatten(turns[last_mutation_turn + 1 :])
    all_calls = _flatten(turns)
    mutations = [
        call for call in all_calls if call.get("name") in mutation_tools
    ]

    final_evidence = report.get("final_evidence", {})
    boundary = final_evidence.get("boundary_facts", {})
    boundary_keys = set(map(str, boundary.get("external_keys", ())))
    actual_keys = {
        str(item.get("key"))
        for item in final_evidence.get("external_deliveries", ())
        if item.get("key")
    }
    expected_scope = str(
        report.get("evaluation", {})
        .get("diagnostics", {})
        .get("semantic_recovery_direction", "")
    )
    required = {RECOVERY_AUDIT_KEY}
    if expected_scope == "compensate_then_discard_candidate":
        required.add(REGISTRY_COMPENSATION_KEY)
    if expected_scope in {
        "publish_committed_cutover",
        "close_already_published_cutover",
    }:
        required.add(REGISTRY_RELEASE_KEY)
    unexpected_keys = actual_keys - boundary_keys - required

    evaluation = report.get("evaluation", {})
    before_facets = _query_facets(before_calls)
    after_facets = _query_facets(after_calls)
    failed_checks = {
        key
        for key, value in evaluation.get("checks", {}).items()
        if not value
    }
    components = evaluation.get("components", {})
    candidate_scope_failed = "candidate_lifecycle_matches_commit_state" in failed_checks
    if evaluation.get("passed", False):
        refined_failure_type = None
    elif (
        candidate_scope_failed
        and before_facets["all_contracts"]
        and before_facets["deployments"]
    ):
        # The agent has enough evidence to know whether the candidate is still
        # useful and the visible serving contract says what to do with unused
        # candidate resources. Leaving or removing the wrong candidate is a
        # repair-scope omission, even if a missing Secret query is an
        # additional investigation gap.
        refined_failure_type = "scope_failure"
    elif not all(before_facets.values()):
        refined_failure_type = "investigation_failure"
    elif not components.get("preservation", True) or not components.get(
        "protocol_safety", True
    ):
        refined_failure_type = "scope_failure"
    elif not components.get("goal_completion", True) or failed_checks & {
        "audit_records_observed_facts",
        "closure_event_records_observed_facts",
    }:
        refined_failure_type = "state_inference_failure"
    elif not components.get("repair_completeness", True):
        refined_failure_type = "execution_failure"
    else:
        refined_failure_type = "verification_failure"
    failure_chain = [refined_failure_type] if refined_failure_type else []
    if (
        refined_failure_type == "scope_failure"
        and candidate_scope_failed
        and not before_facets["candidate_secret"]
    ):
        failure_chain.insert(0, "investigation_failure")
    post_verification = all(
        after_facets[key]
        for key in (
            "catalog",
            "migration_jobs",
            "deployments",
            "candidate_secret",
            "service",
            "external_registry",
            "closure_records",
        )
    )
    if refined_failure_type and post_verification:
        failure_chain.append("verification_failure")
    return {
        "variant": report.get("variant"),
        "passed": bool(evaluation.get("passed", False)),
        "primary_error": report.get("trajectory_diagnostics", {}).get(
            "primary_error"
        ),
        "refined_failure_type": refined_failure_type,
        "failure_chain": failure_chain,
        "turn_count": len(turns),
        "first_mutation_turn": (
            first_mutation_turn + 1 if mutation_turns else None
        ),
        "last_mutation_turn": last_mutation_turn + 1 if mutation_turns else None,
        "pre_mutation_facets": before_facets,
        "pre_mutation_full_reconstruction": all(before_facets.values()),
        "post_mutation_facets": after_facets,
        "post_mutation_cross_system_verification": post_verification,
        "mutation_signature": [_mutation_signature(call) for call in mutations],
        "unexpected_external_keys": sorted(unexpected_keys),
        "boundary_relative_integrity": (
            bool(evaluation.get("passed", False)) and not unexpected_keys
        ),
        "failed_checks": sorted(failed_checks),
    }


def analyze_kubernetes_constraint_runs(
    reports: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    rows = [analyze_kubernetes_constraint_report(report) for report in reports]
    failures = Counter(
        str(row["refined_failure_type"] or "unclassified")
        for row in rows
        if not row["passed"]
    )
    return {
        "schema_version": "1.0",
        "completed_runs": len(rows),
        "pass_rate": (sum(row["passed"] for row in rows) / len(rows) if rows else 0),
        "boundary_relative_integrity_rate": (
            sum(row["boundary_relative_integrity"] for row in rows) / len(rows)
            if rows
            else 0
        ),
        "pre_mutation_full_reconstruction_rate": (
            sum(row["pre_mutation_full_reconstruction"] for row in rows) / len(rows)
            if rows
            else 0
        ),
        "post_mutation_cross_system_verification_rate": (
            sum(row["post_mutation_cross_system_verification"] for row in rows)
            / len(rows)
            if rows
            else 0
        ),
        "unexpected_external_effect_run_count": sum(
            bool(row["unexpected_external_keys"]) for row in rows
        ),
        "mean_turn_count": mean(row["turn_count"] for row in rows) if rows else 0,
        "failure_type_counts": dict(sorted(failures.items())),
        "reports": rows,
    }


def load_run_reports(root: Path) -> list[dict[str, Any]]:
    import json

    reports = []
    for path in sorted(root.rglob("*.json")):
        if path.name.endswith("-failure.json") or path.name in {
            "summary.json",
            "analysis.json",
            "prefix.json",
        }:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("family") == "k8s-constraint-scope-recovery":
            reports.append(payload)
    return reports
