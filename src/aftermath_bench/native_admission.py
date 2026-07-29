from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .evidence_replay import replay_graph
from .native_scenario import NativeScenario


@dataclass(frozen=True)
class NativeAdmissionReport:
    scenario_id: str
    requested_tier: str
    admitted_tier: str
    passed: bool
    checks: dict[str, bool]
    observed: dict[str, int | float | bool]
    artifact_sha256: dict[str, str]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, passed in self.checks.items() if not passed)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dependency_depth(
    nodes: Iterable[str],
    relations: Iterable[dict[str, Any]],
) -> int:
    node_set = set(nodes)
    adjacency: dict[str, list[str]] = {node: [] for node in node_set}
    indegree: dict[str, int] = {node: 0 for node in node_set}
    for relation in relations:
        source = str(relation["source"])
        target = str(relation["target"])
        if source not in node_set or target not in node_set:
            return 0
        adjacency[source].append(target)
        indegree[target] += 1

    queue = [node for node, degree in indegree.items() if degree == 0]
    depth = {node: 1 for node in queue}
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for target in adjacency[node]:
            depth[target] = max(depth.get(target, 1), depth[node] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if visited != len(node_set):
        return 0
    return max(depth.values(), default=0)


def _shared_dependency_count(
    protected_effects: Iterable[str],
    relations: Iterable[dict[str, Any]],
) -> int:
    protected = set(protected_effects)
    degree: Counter[str] = Counter()
    for relation in relations:
        degree[str(relation["source"])] += 1
        degree[str(relation["target"])] += 1
    return sum(1 for node in protected if degree[node] >= 3)


def _recovery_signature(report: dict[str, Any]) -> tuple[tuple[str, int], ...]:
    return tuple(
        sorted(Counter(map(str, report.get("mutation_tools", ()))).items())
    )


def _varying_action_branch_count(
    reports: Iterable[dict[str, Any]],
    action_branches: Iterable[dict[str, Any]],
) -> int:
    branch_tools = {
        str(branch["id"]): set(map(str, branch.get("mutation_tools", ())))
        for branch in action_branches
    }
    reports = tuple(reports)
    varying = 0
    for tools in branch_tools.values():
        counts = {
            sum(
                1
                for tool in report.get("mutation_tools", ())
                if str(tool) in tools
            )
            for report in reports
        }
        if len(counts) > 1:
            varying += 1
    return varying


def _reference_evidence_groups(
    query_tools: set[str],
    graph: dict[str, Any],
) -> dict[str, bool]:
    configured = graph.get("evidence_tool_groups")
    if configured:
        return {
            str(group["id"]): bool(
                query_tools & set(map(str, group.get("tools", ())))
            )
            for group in configured
        }
    return {
        "documents": bool(query_tools & {"get_document", "list_documents"}),
        "ledgers": bool(
            query_tools & {"get_stock_ledger", "get_general_ledger"}
        ),
        "async": bool(
            query_tools
            & {"find_background_jobs", "wait_for_external_delivery"}
        ),
        "external": bool(
            query_tools
            & {"get_external_delivery", "wait_for_external_delivery"}
        ),
    }


def validate_native_scenario(
    scenario: NativeScenario,
) -> NativeAdmissionReport:
    prefix_path = scenario.resolve_artifact("prefix")
    reference_path = scenario.resolve_artifact("reference")
    graph_path = scenario.resolve_artifact("observed_graph")
    baseline_path = scenario.resolve_artifact("baselines")
    replay_path = (
        scenario.resolve_artifact("replay_evidence")
        if "replay_evidence" in scenario.raw.get("admission_artifacts", {})
        else None
    )
    paths = {
        "prefix": prefix_path,
        "reference": reference_path,
        "observed_graph": graph_path,
        "baselines": baseline_path,
    }
    if replay_path is not None:
        paths["replay_evidence"] = replay_path
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        checks = {f"artifact_exists:{name}": False for name in missing}
        return NativeAdmissionReport(
            scenario_id=scenario.scenario_id,
            requested_tier=scenario.tier,
            admitted_tier="invalid",
            passed=False,
            checks=checks,
            observed={"missing_artifact_count": len(missing)},
            artifact_sha256={},
        )

    prefix = _load_json(prefix_path)
    reference = _load_json(reference_path)
    graph = _load_json(graph_path)
    baselines = _load_json(baseline_path)
    replay_evidence = _load_json(replay_path) if replay_path else None

    trace = prefix.get("trace", ())
    successful_prefix_writes = sum(
        1
        for event in trace
        if event.get("kind") == "write"
        and event.get("status", "success") == "success"
    )
    protected_effects = graph.get("protected_effects", ())
    entities = graph.get("entities", ())
    entity_ids = {str(entity["id"]) for entity in entities}
    relations = graph.get("relations", ())
    relation_types = {str(relation["type"]) for relation in relations}
    variants = reference.get("reports", ())
    variant_ids = {str(report["variant"]) for report in variants}
    expected_variants = set(scenario.variants)
    mutation_counts = [
        len(report.get("mutation_tools", ()))
        if "mutation_tools" in report
        else int(report.get("selected_mutation") is not None)
        for report in variants
    ]
    downstream_repairs = [
        int(report.get("downstream_repairs", 0)) for report in variants
    ]
    passed_references = [
        bool(report.get("passed", False)) for report in variants
    ]
    reference_query_groups = []
    for report in variants:
        reference_query_groups.append(
            _reference_evidence_groups(
                set(map(str, report.get("query_tools", ()))),
                graph,
            )
        )
    minimum_reference_evidence_groups = min(
        (
            sum(bool(value) for value in groups.values())
            for groups in reference_query_groups
        ),
        default=0,
    )
    heuristic_rates = [
        float(item.get("pass_rate", 1.0))
        for item in baselines.get("heuristics", ())
    ]
    matched_heuristic_successes = [
        bool(item.get("matched_group_success", True))
        for item in baselines.get("heuristics", ())
    ]

    minimum_mutations = min(mutation_counts, default=0)
    minimum_downstream_repairs = min(downstream_repairs, default=0)
    maximum_heuristic_pass_rate = max(heuristic_rates, default=1.0)
    depth = _dependency_depth(entity_ids, relations)
    evidence_groups = graph.get("required_evidence_groups", ())
    single_query_decisive = bool(graph.get("single_query_decisive", True))
    minimum_boundary_query_groups = int(
        graph.get("minimum_boundary_query_groups", 0)
    )
    replay_results = (
        replay_graph(graph, replay_evidence)
        if replay_evidence is not None
        else ()
    )
    relations_observed = bool(replay_results) and all(
        result.passed for result in replay_results
    )
    replayed_relation_count = sum(
        1 for result in replay_results if result.passed
    )
    unsafe_actions = graph.get("unsafe_actions", ())
    shared_dependencies = _shared_dependency_count(
        protected_effects,
        relations,
    )
    recovery_signatures = {
        _recovery_signature(report) for report in variants
    }
    action_branches = graph.get("action_branches", ())
    varying_branches = _varying_action_branch_count(
        variants,
        action_branches,
    )

    observed: dict[str, int | float | bool] = {
        "successful_prefix_writes": successful_prefix_writes,
        "protected_effect_count": len(protected_effects),
        "relevant_entity_count": len(entity_ids),
        "semantic_edge_count": len(relations),
        "relation_type_count": len(relation_types),
        "dependency_depth": depth,
        "evidence_group_count": len(evidence_groups),
        "minimum_reference_evidence_groups": (
            minimum_reference_evidence_groups
        ),
        "single_query_decisive": single_query_decisive,
        "minimum_boundary_query_groups": minimum_boundary_query_groups,
        "all_relations_observed": relations_observed,
        "replayed_relation_count": replayed_relation_count,
        "minimum_repair_mutations": minimum_mutations,
        "minimum_downstream_repairs": minimum_downstream_repairs,
        "unsafe_action_count": len(unsafe_actions),
        "action_branch_count": len(action_branches),
        "shared_dependency_count": shared_dependencies,
        "distinct_recovery_signature_count": len(recovery_signatures),
        "varying_action_branch_count": varying_branches,
        "maximum_heuristic_pass_rate": maximum_heuristic_pass_rate,
    }
    checks = {
        "variant_coverage_complete": variant_ids == expected_variants,
        "reference_recovery_passes": (
            len(passed_references) == len(expected_variants)
            and all(passed_references)
        ),
        "prefix_writes>=8": successful_prefix_writes >= 8,
        "protected_effects>=3": len(protected_effects) >= 3,
        "relevant_entities>=20": len(entity_ids) >= 20,
        "dependency_depth>=5": depth >= 5,
        "relation_types>=8": len(relation_types) >= 8,
        "evidence_groups>=4": len(evidence_groups) >= 4,
        "reference_uses_four_evidence_groups": (
            minimum_reference_evidence_groups >= 4
        ),
        "no_single_query_is_decisive": not single_query_decisive,
        "minimum_boundary_query_groups>=2": (
            minimum_boundary_query_groups >= 2
        ),
        "all_relations_have_replay_evidence": relations_observed,
        "minimum_mutations>=4": minimum_mutations >= 4,
        "downstream_repairs>=2": minimum_downstream_repairs >= 2,
        "shared_dependencies>=2": shared_dependencies >= 2,
        "unsafe_actions>=3": len(unsafe_actions) >= 3,
        "action_branches>=3": len(action_branches) >= 3,
        "recovery_signatures>=3": len(recovery_signatures) >= 3,
        "varying_action_branches>=2": varying_branches >= 2,
        "heuristic_pass_rate<0.5": maximum_heuristic_pass_rate < 0.5,
        "heuristic_matched_group_zero": not any(
            matched_heuristic_successes
        ),
    }
    hard_passed = all(checks.values())
    requested_tier = scenario.tier
    candidate_passed = all(
        value
        for name, value in checks.items()
        if name != "minimum_mutations>=4"
    ) and minimum_mutations >= 3
    admitted_tier = (
        "hard"
        if hard_passed
        else "candidate"
        if candidate_passed
        else "easy"
    )
    if requested_tier == "hard":
        tier_consistent = hard_passed
    elif requested_tier == "candidate":
        tier_consistent = admitted_tier == "candidate"
    elif requested_tier == "easy":
        tier_consistent = admitted_tier == "easy"
    else:
        tier_consistent = False
    checks["declared_tier_is_truthful"] = tier_consistent
    return NativeAdmissionReport(
        scenario_id=scenario.scenario_id,
        requested_tier=requested_tier,
        admitted_tier=admitted_tier,
        passed=tier_consistent,
        checks=checks,
        observed=observed,
        artifact_sha256={
            name: _sha256(path) for name, path in paths.items()
        },
    )
