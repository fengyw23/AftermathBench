from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .schema import Relation, TaskSpec


@dataclass(frozen=True)
class AdmissionReport:
    task_id: str
    passed: bool
    checks: dict[str, bool]
    observed: dict[str, int]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, passed in self.checks.items() if not passed)


def _dependency_depth(nodes: Iterable[str], relations: Iterable[Relation]) -> int:
    adjacency: dict[str, list[str]] = {node: [] for node in nodes}
    indegree: dict[str, int] = {node: 0 for node in nodes}
    for relation in relations:
        adjacency.setdefault(relation.source, []).append(relation.target)
        adjacency.setdefault(relation.target, [])
        indegree.setdefault(relation.source, 0)
        indegree[relation.target] = indegree.get(relation.target, 0) + 1

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

    if visited != len(indegree):
        # Cycles are a valid recovery motif, but depth must be supplied by the
        # acyclic causal projection rather than silently underestimated.
        return 0
    return max(depth.values(), default=0)


def validate_task(task: TaskSpec) -> AdmissionReport:
    raw = task.raw
    successful_prefix_writes = sum(
        1
        for step in raw["prefix_trace"]
        if step.get("kind") == "write" and step.get("status") == "success"
    )
    entity_ids = {item["id"] for item in raw["entities"]}
    relation_types = {item["type"] for item in raw["relations"]}
    hidden_outcomes = {item["hidden_outcome"] for item in raw["variants"]}
    min_mutations = min(item["minimum_repair_mutations"] for item in raw["variants"])
    depth = _dependency_depth(entity_ids, task.relations)

    observed = {
        "successful_prefix_writes": successful_prefix_writes,
        "system_count": len(set(raw["systems"])),
        "protected_effect_count": len(raw["protected_effects"]),
        "relevant_entity_count": len(entity_ids),
        "semantic_edge_count": len(raw["relations"]),
        "relation_type_count": len(relation_types),
        "dependency_depth": depth,
        "nonlinear_motif_count": len(set(raw["nonlinear_motifs"])),
        "commit_state_hypothesis_count": len(hidden_outcomes),
        "evidence_source_count": len(set(raw["required_evidence_sources"])),
        "minimum_repair_mutations": min_mutations,
        "minimum_downstream_repairs": int(raw["minimum_downstream_repairs"]),
        "unsafe_retry_action_count": len(set(raw["unsafe_retry_actions"])),
    }
    checks = {
        "prefix_writes>=6": successful_prefix_writes >= 6,
        "systems>=2": observed["system_count"] >= 2,
        "protected_effects>=3": observed["protected_effect_count"] >= 3,
        "entities>=20": observed["relevant_entity_count"] >= 20,
        "relations>=28": observed["semantic_edge_count"] >= 28,
        "relation_types>=4": observed["relation_type_count"] >= 4,
        "dependency_depth>=4": depth >= 4,
        "nonlinear_motifs>=2": observed["nonlinear_motif_count"] >= 2,
        "commit_hypotheses>=3": observed["commit_state_hypothesis_count"] >= 3,
        "evidence_sources>=3": observed["evidence_source_count"] >= 3,
        "minimum_mutations>=3": min_mutations >= 3,
        "downstream_repairs>=2": observed["minimum_downstream_repairs"] >= 2,
        "unsafe_retry_actions>=1": observed["unsafe_retry_action_count"] >= 1,
        "relation_endpoints_exist": all(
            relation.source in entity_ids and relation.target in entity_ids
            for relation in task.relations
        ),
    }
    return AdmissionReport(
        task_id=task.task_id,
        passed=all(checks.values()),
        checks=checks,
        observed=observed,
    )
