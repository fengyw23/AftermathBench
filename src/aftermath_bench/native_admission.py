from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evidence_replay import replay_graph
from .native_scenario import NativeScenario
from .obligation_interaction_audit import analyze_obligation_interactions
from .scope_decision_audit import analyze_scope_decision_matrix


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


def native_admission_report_payload(
    report: NativeAdmissionReport,
) -> dict[str, Any]:
    """Return the canonical persisted representation of an admission result.

    The report binds only the evidence consumed by admission.  The persisted
    report file is a derived release artifact and therefore cannot include
    its own hash without creating a circular dependency.
    """

    return {
        "scenario_id": report.scenario_id,
        "requested_tier": report.requested_tier,
        "admitted_tier": report.admitted_tier,
        "passed": report.passed,
        "checks": report.checks,
        "observed": report.observed,
        "failures": list(report.failures),
        "artifact_sha256": report.artifact_sha256,
    }


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
    return tuple(sorted(Counter(map(str, report.get("mutation_tools", ()))).items()))


def _canonical_call(event: dict[str, Any]) -> str:
    """Return a stable semantic signature for a replayed public-tool call."""

    return json.dumps(
        {
            "tool": str(event.get("tool", "")),
            "arguments": event.get("arguments", {}),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _leaf_tokens(value: Any, *, key: str = "") -> set[tuple[str, str]]:
    """Extract conservative identifier-like tokens from a replay result.

    Query adaptivity is only credited when a later public call consumes a
    value returned by an earlier call.  Status words, booleans and other
    low-information values are deliberately ignored so that repeated polling
    cannot manufacture a long investigation chain.
    """

    if isinstance(value, dict):
        tokens: set[tuple[str, str]] = set()
        for child_key, child in value.items():
            tokens.update(_leaf_tokens(child, key=str(child_key)))
        return tokens
    if isinstance(value, (list, tuple)):
        tokens: set[tuple[str, str]] = set()
        for child in value:
            tokens.update(_leaf_tokens(child, key=key))
        return tokens
    if value is None or isinstance(value, bool):
        return set()

    normalised_key = re.sub(r"[^a-z0-9]+", "", key.lower())
    if isinstance(value, int):
        if "id" not in normalised_key and "index" not in normalised_key:
            return set()
        return {("identifier", str(value))}
    if not isinstance(value, str):
        return set()

    text = value.strip()
    if not text:
        return set()
    if normalised_key in {"content", "body"} and text[:1] in {"{", "["}:
        try:
            decoded = json.loads(text)
        except (TypeError, ValueError):
            pass
        else:
            return _leaf_tokens(decoded)
    ignored = {
        "success",
        "failure",
        "failed",
        "waiting",
        "queued",
        "running",
        "ready",
        "open",
        "closed",
        "main",
        "true",
        "false",
    }
    if text.lower() in ignored:
        return set()
    if (
        "id" in normalised_key
        or "index" in normalised_key
        or "sha" in normalised_key
        or "digest" in normalised_key
        or "name" in normalised_key
        or "path" in normalised_key
        or len(text) >= 8
    ):
        return {("identifier", text)}
    return set()


def _argument_tokens(value: Any, *, key: str = "") -> set[tuple[str, str]]:
    """Extract values that can be proved to have come from an earlier result."""

    if isinstance(value, dict):
        tokens: set[tuple[str, str]] = set()
        for child_key, child in value.items():
            tokens.update(_argument_tokens(child, key=str(child_key)))
        return tokens
    if isinstance(value, (list, tuple)):
        tokens: set[tuple[str, str]] = set()
        for child in value:
            tokens.update(_argument_tokens(child, key=key))
        return tokens
    if value is None or isinstance(value, bool):
        return set()
    normalised_key = re.sub(r"[^a-z0-9]+", "", key.lower())
    if isinstance(value, int):
        if "id" in normalised_key or "index" in normalised_key:
            return {("identifier", str(value))}
        return set()
    if isinstance(value, str):
        text = value.strip()
        if text:
            return {("identifier", text)}
    return set()


def _adaptive_query_depth(report: dict[str, Any]) -> int:
    """Measure replay-proven read-after-read discovery depth.

    Identical query signatures are collapsed before building the dependency
    DAG.  This prevents a polling loop from being mistaken for adaptive state
    reconstruction.
    """

    events = []
    seen: set[str] = set()
    for raw in report.get("query_events", ()):
        if "result" not in raw:
            continue
        signature = _canonical_call(raw)
        if signature in seen:
            continue
        seen.add(signature)
        events.append(raw)
    if not events:
        return 0

    result_tokens = [_leaf_tokens(event.get("result")) for event in events]
    argument_tokens = [_argument_tokens(event.get("arguments", {})) for event in events]
    depth = [1] * len(events)
    for target in range(len(events)):
        for source in range(target):
            if result_tokens[source] & argument_tokens[target]:
                depth[target] = max(depth[target], depth[source] + 1)
    return max(depth, default=0)


def _edit_distance(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_item in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_item in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_item != right_item),
                )
            )
        previous = current
    return previous[-1]


def _mutation_sequence(report: dict[str, Any]) -> tuple[str, ...]:
    events = report.get("mutation_events")
    if events:
        return tuple(_canonical_call(event) for event in events)
    return tuple(map(str, report.get("mutation_tools", ())))


def _recovery_divergence(
    reports: Iterable[dict[str, Any]],
) -> tuple[int, int, int]:
    """Return common-tail length, minimum branch prefix and pairwise distance."""

    sequences = tuple(_mutation_sequence(report) for report in reports)
    if not sequences:
        return 0, 0, 0
    common_tail = 0
    while all(len(sequence) > common_tail for sequence in sequences):
        candidate = sequences[0][-(common_tail + 1)]
        if not all(sequence[-(common_tail + 1)] == candidate for sequence in sequences):
            break
        common_tail += 1
    minimum_branch_prefix = min(len(sequence) - common_tail for sequence in sequences)
    pairwise = [
        _edit_distance(sequences[left], sequences[right])
        for left in range(len(sequences))
        for right in range(left + 1, len(sequences))
    ]
    return common_tail, minimum_branch_prefix, min(pairwise, default=0)


def _normalise_prompt_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _constraint_prompt_admission(
    audit: dict[str, Any],
    *,
    minimum_counterfactual_flips: int,
    expected_variants: set[str],
) -> tuple[dict[str, bool], dict[str, int | float | bool]]:
    surfaces = tuple(audit.get("visible_surfaces", ()))
    surface_ids = [str(item.get("id", "")) for item in surfaces]
    required_surface_ids = set(map(str, audit.get("required_surface_ids", ())))
    nonempty_surfaces = [item for item in surfaces if str(item.get("text", "")).strip()]
    surface_hashes_match = all(
        str(item.get("sha256", ""))
        == hashlib.sha256(str(item.get("text", "")).encode("utf-8")).hexdigest()
        for item in surfaces
    )
    labels = {
        _normalise_prompt_text(str(label))
        for label in audit.get("forbidden_direction_labels", ())
        if _normalise_prompt_text(str(label))
    }
    normalised_surfaces = {
        str(item.get("id", "")): _normalise_prompt_text(str(item.get("text", "")))
        for item in surfaces
    }
    leaked_pairs = {
        (surface_id, label)
        for surface_id, text in normalised_surfaces.items()
        for label in labels
        if label in text
    }

    groups = {
        str(group["id"]): set(map(str, group.get("surface_ids", ())))
        for group in audit.get("constraint_evidence_groups", ())
    }
    group_sources_valid = bool(groups) and all(
        sources and sources <= set(surface_ids) for sources in groups.values()
    )
    constraints = {
        str(item["id"]): set(map(str, item.get("surface_ids", ())))
        for item in audit.get("constraints", ())
    }
    constraint_sources_valid = bool(constraints) and all(
        sources and sources <= set(surface_ids) for sources in constraints.values()
    )
    derivations = tuple(audit.get("variant_derivations", ()))
    derivation_ids = {str(item.get("variant", "")) for item in derivations}
    derivation_group_counts = [
        len(set(map(str, item.get("evidence_groups", ())))) for item in derivations
    ]
    derivation_constraint_counts = [
        len(set(map(str, item.get("constraint_ids", ())))) for item in derivations
    ]
    decisive_surface_counts = [
        len(set(map(str, item.get("decisive_surface_ids", ())))) for item in derivations
    ]
    derivations_reference_known_groups = bool(derivations) and all(
        set(map(str, item.get("evidence_groups", ()))) <= set(groups)
        for item in derivations
    )
    derivations_reference_known_constraints = bool(derivations) and all(
        set(map(str, item.get("constraint_ids", ()))) <= set(constraints)
        for item in derivations
    )
    derivation_surfaces_visible = bool(derivations) and all(
        set(map(str, item.get("decisive_surface_ids", ()))) <= set(surface_ids)
        for item in derivations
    )
    flips = tuple(audit.get("counterfactual_pairs", ()))
    valid_flips = sum(
        1
        for item in flips
        if int(item.get("changed_fact_count", 0)) == 1
        and bool(item.get("direction_flipped", False))
    )

    minimum_groups = min(derivation_group_counts, default=0)
    minimum_constraints = min(derivation_constraint_counts, default=0)
    minimum_decisive_surfaces = min(decisive_surface_counts, default=0)
    observed: dict[str, int | float | bool] = {
        "ordinary_visible_surface_count": len(surfaces),
        "ordinary_required_surface_count": len(required_surface_ids),
        "ordinary_direction_label_leak_count": len(leaked_pairs),
        "constraint_evidence_group_count": len(groups),
        "visible_constraint_count": len(constraints),
        "minimum_derivation_evidence_groups": minimum_groups,
        "minimum_derivation_constraints": minimum_constraints,
        "minimum_decisive_surfaces": minimum_decisive_surfaces,
        "single_fact_direction_flip_count": valid_flips,
    }
    checks = {
        "ordinary_prompt_surfaces_complete": (
            bool(surfaces)
            and len(surface_ids) == len(set(surface_ids))
            and required_surface_ids <= set(surface_ids)
            and len(nonempty_surfaces) == len(surfaces)
        ),
        "ordinary_prompt_surface_hashes_match": surface_hashes_match,
        "ordinary_direction_labels_not_leaked": not leaked_pairs,
        "constraint_evidence_groups>=4": len(groups) >= 4,
        "constraint_group_sources_are_visible": group_sources_valid,
        "constraint_sources_are_visible": constraint_sources_valid,
        "variant_derivations_cover_all_variants": derivation_ids == expected_variants,
        "derivations_reference_known_groups": derivations_reference_known_groups,
        "derivations_reference_known_constraints": (
            derivations_reference_known_constraints
        ),
        "derivation_surfaces_are_visible": derivation_surfaces_visible,
        "each_scope_uses_three_evidence_groups": minimum_groups >= 3,
        "each_scope_uses_two_constraints": minimum_constraints >= 2,
        "no_single_visible_surface_is_decisive": minimum_decisive_surfaces >= 3,
        "single_fact_counterfactual_flips_meet_profile": (
            valid_flips >= minimum_counterfactual_flips
        ),
    }
    return checks, observed


def _projection_witness_admission(
    report: dict[str, Any],
    *,
    expected_variants: set[str],
    minimum_witnesses: int,
) -> tuple[dict[str, bool], dict[str, int | float | bool]]:
    witnesses = report.get("witnesses", {})
    if not isinstance(witnesses, dict):
        witnesses = {}
    variant_ids = set(map(str, report.get("variant_ids", ())))
    valid_witnesses = 0
    for witness in witnesses.values():
        if not isinstance(witness, dict):
            continue
        left = str(witness.get("left_variant", ""))
        right = str(witness.get("right_variant", ""))
        left_scope = str(witness.get("left_scope", ""))
        right_scope = str(witness.get("right_scope", ""))
        removed = tuple(map(str, witness.get("removed_fact_keys", ())))
        if (
            left in expected_variants
            and right in expected_variants
            and left != right
            and left_scope
            and right_scope
            and left_scope != right_scope
            and bool(removed)
        ):
            valid_witnesses += 1
    declared_group_count = int(report.get("evidence_group_count", 0))
    observed: dict[str, int | float | bool] = {
        "projection_variant_count": len(variant_ids),
        "projection_evidence_group_count": declared_group_count,
        "valid_projection_witness_count": valid_witnesses,
    }
    checks = {
        "projection_variants_cover_all_variants": variant_ids == expected_variants,
        "projection_group_count_matches_report": (
            declared_group_count == len(witnesses)
        ),
        "projection_witnesses_meet_profile": valid_witnesses >= minimum_witnesses,
        "every_declared_evidence_group_has_projection_witness": (
            bool(witnesses)
            and valid_witnesses == len(witnesses)
            and bool(report.get("all_declared_groups_have_witnesses", False))
        ),
    }
    return checks, observed


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
            sum(1 for tool in report.get("mutation_tools", ()) if str(tool) in tools)
            for report in reports
        }
        if len(counts) > 1:
            varying += 1
    return varying


def _reference_evidence_groups(
    query_source: set[str] | dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, bool]:
    if isinstance(query_source, dict):
        query_tools = set(map(str, query_source.get("query_tools", ())))
        query_events = tuple(query_source.get("query_events", ()))
    else:
        query_tools = query_source
        query_events = ()
    configured = graph.get("evidence_tool_groups")
    if configured:
        results: dict[str, bool] = {}
        for group in configured:
            call_specs = tuple(group.get("calls", ()))
            if call_specs:
                results[str(group["id"])] = any(
                    str(event.get("tool")) == str(spec.get("tool"))
                    and all(
                        event.get("arguments", {}).get(key) == value
                        for key, value in spec.get("arguments", {}).items()
                    )
                    for event in query_events
                    for spec in call_specs
                )
            else:
                results[str(group["id"])] = bool(
                    query_tools & set(map(str, group.get("tools", ())))
                )
        return results
    return {
        "documents": bool(query_tools & {"get_document", "list_documents"}),
        "ledgers": bool(query_tools & {"get_stock_ledger", "get_general_ledger"}),
        "async": bool(
            query_tools & {"find_background_jobs", "wait_for_external_delivery"}
        ),
        "external": bool(
            query_tools & {"get_external_delivery", "wait_for_external_delivery"}
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
    # admission.json is the derived result of this validation.  Treating it
    # as an input creates an impossible self-reference for a freshly built
    # scenario and records the hash of a provisional report rather than the
    # report that is ultimately published.
    constraint_profile = scenario.raw.get("admission_profile", {}).get(
        "constraint_derived_scope", {}
    )
    scope_decision_profile = scenario.raw.get("admission_profile", {}).get(
        "scope_decision", {}
    )
    obligation_profile = scenario.raw.get("admission_profile", {}).get(
        "obligation_interaction", {}
    )
    if constraint_profile:
        paths["prompt_audit"] = scenario.resolve_artifact("prompt_audit")
        if bool(constraint_profile.get("require_projection_witnesses", False)):
            paths["projection_witnesses"] = scenario.resolve_artifact(
                "projection_witnesses"
            )
    if replay_path is not None:
        paths["replay_evidence"] = replay_path
    if scope_decision_profile:
        paths["scope_decision_matrix"] = scenario.resolve_artifact(
            "scope_decision_matrix"
        )
    if obligation_profile:
        paths["obligation_interactions"] = scenario.resolve_artifact(
            "obligation_interactions"
        )
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
    prompt_audit = (
        _load_json(paths["prompt_audit"]) if "prompt_audit" in paths else None
    )
    projection_witnesses = (
        _load_json(paths["projection_witnesses"])
        if "projection_witnesses" in paths
        else None
    )
    artifact_payloads = {name: _load_json(path) for name, path in paths.items()}
    artifact_scenario_ids_match = all(
        str(payload.get("scenario_id", "")) == scenario.scenario_id
        for payload in artifact_payloads.values()
    )

    trace = prefix.get("trace", ())
    successful_prefix_writes = sum(
        1
        for event in trace
        if event.get("kind") == "write" and event.get("status", "success") == "success"
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
        (
            len(report.get("mutation_tools", ()))
            if "mutation_tools" in report
            else int(report.get("selected_mutation") is not None)
        )
        for report in variants
    ]
    downstream_repairs = [
        int(report.get("downstream_repairs", 0)) for report in variants
    ]
    passed_references = [bool(report.get("passed", False)) for report in variants]
    reference_query_groups = []
    for report in variants:
        reference_query_groups.append(_reference_evidence_groups(report, graph))
    minimum_reference_evidence_groups = min(
        (
            sum(bool(value) for value in groups.values())
            for groups in reference_query_groups
        ),
        default=0,
    )
    heuristic_rates = [
        float(item.get("pass_rate", 1.0)) for item in baselines.get("heuristics", ())
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
    minimum_boundary_query_groups = int(graph.get("minimum_boundary_query_groups", 0))
    replay_results = (
        replay_graph(graph, replay_evidence) if replay_evidence is not None else ()
    )
    replay_capture_variants = (
        [
            str(capture.get("variant", ""))
            for capture in replay_evidence.get("captures", ())
        ]
        if replay_evidence is not None
        else []
    )
    replay_capture_coverage_complete = bool(replay_evidence) and (
        len(replay_capture_variants) == len(set(replay_capture_variants))
        and set(replay_capture_variants) == expected_variants
    )
    relations_observed = bool(replay_results) and all(
        result.passed for result in replay_results
    )
    replayed_relation_count = sum(1 for result in replay_results if result.passed)
    unsafe_actions = graph.get("unsafe_actions", ())
    shared_dependencies = _shared_dependency_count(
        protected_effects,
        relations,
    )
    recovery_signatures = {_recovery_signature(report) for report in variants}
    semantic_directions = {
        str(report["semantic_recovery_direction"])
        for report in variants
        if report.get("semantic_recovery_direction")
    }
    required_semantic_directions = int(
        graph.get("minimum_semantic_recovery_directions", 0)
    )
    action_branches = graph.get("action_branches", ())
    varying_branches = _varying_action_branch_count(
        variants,
        action_branches,
    )
    reasoning_profile = scenario.raw.get("admission_profile", {}).get(
        "adaptive_recovery", {}
    )
    adaptive_depths = [_adaptive_query_depth(report) for report in variants]
    minimum_adaptive_query_depth = min(adaptive_depths, default=0)
    (
        common_completion_tail_length,
        minimum_variant_specific_mutations,
        minimum_pairwise_mutation_distance,
    ) = _recovery_divergence(variants)

    observed: dict[str, int | float | bool] = {
        "successful_prefix_writes": successful_prefix_writes,
        "protected_effect_count": len(protected_effects),
        "relevant_entity_count": len(entity_ids),
        "semantic_edge_count": len(relations),
        "relation_type_count": len(relation_types),
        "dependency_depth": depth,
        "evidence_group_count": len(evidence_groups),
        "minimum_reference_evidence_groups": (minimum_reference_evidence_groups),
        "single_query_decisive": single_query_decisive,
        "minimum_boundary_query_groups": minimum_boundary_query_groups,
        "all_relations_observed": relations_observed,
        "replayed_relation_count": replayed_relation_count,
        "replay_capture_count": len(replay_capture_variants),
        "minimum_repair_mutations": minimum_mutations,
        "minimum_downstream_repairs": minimum_downstream_repairs,
        "unsafe_action_count": len(unsafe_actions),
        "action_branch_count": len(action_branches),
        "shared_dependency_count": shared_dependencies,
        "distinct_recovery_signature_count": len(recovery_signatures),
        "semantic_recovery_direction_count": len(semantic_directions),
        "required_semantic_recovery_direction_count": (required_semantic_directions),
        "varying_action_branch_count": varying_branches,
        "maximum_heuristic_pass_rate": maximum_heuristic_pass_rate,
        "artifact_identity_count": len(artifact_payloads),
    }
    checks = {
        "variant_coverage_complete": variant_ids == expected_variants,
        "reference_recovery_passes": (
            len(passed_references) == len(expected_variants) and all(passed_references)
        ),
        "prefix_writes>=8": successful_prefix_writes >= 8,
        "protected_effects>=3": len(protected_effects) >= 3,
        "relevant_entities>=20": len(entity_ids) >= 20,
        "dependency_depth>=5": depth >= 5,
        "relation_types>=8": len(relation_types) >= 8,
        "evidence_groups>=4": len(evidence_groups) >= 4,
        "reference_uses_four_evidence_groups": (minimum_reference_evidence_groups >= 4),
        "no_single_query_is_decisive": not single_query_decisive,
        "minimum_boundary_query_groups>=2": (minimum_boundary_query_groups >= 2),
        "all_relations_have_replay_evidence": relations_observed,
        "replay_captures_cover_variants_exactly_once": (
            replay_capture_coverage_complete
        ),
        "minimum_mutations>=4": minimum_mutations >= 4,
        "downstream_repairs>=2": minimum_downstream_repairs >= 2,
        "shared_dependencies>=2": shared_dependencies >= 2,
        "unsafe_actions>=3": len(unsafe_actions) >= 3,
        "action_branches>=3": len(action_branches) >= 3,
        "recovery_signatures>=3": len(recovery_signatures) >= 3,
        "semantic_recovery_directions_meet_profile": (
            required_semantic_directions == 0
            or len(semantic_directions) >= required_semantic_directions
        ),
        "varying_action_branches>=2": varying_branches >= 2,
        "heuristic_pass_rate<0.5": maximum_heuristic_pass_rate < 0.5,
        "heuristic_matched_group_zero": not any(matched_heuristic_successes),
        "artifact_scenario_ids_match": artifact_scenario_ids_match,
    }
    if reasoning_profile:
        observed.update(
            {
                "minimum_adaptive_query_depth": minimum_adaptive_query_depth,
                "common_completion_tail_length": common_completion_tail_length,
                "minimum_variant_specific_mutations": (
                    minimum_variant_specific_mutations
                ),
                "minimum_pairwise_mutation_distance": (
                    minimum_pairwise_mutation_distance
                ),
            }
        )
        required_depth = int(reasoning_profile.get("minimum_adaptive_query_depth", 2))
        required_variant_mutations = int(
            reasoning_profile.get("minimum_variant_specific_mutations", 2)
        )
        required_pairwise_distance = int(
            reasoning_profile.get("minimum_pairwise_mutation_distance", 2)
        )
        checks.update(
            {
                "reference_queries_include_replayed_results": all(
                    bool(report.get("query_events"))
                    and all("result" in event for event in report["query_events"])
                    for report in variants
                ),
                "adaptive_query_depth_meets_profile": (
                    minimum_adaptive_query_depth >= required_depth
                ),
                "variant_specific_mutations_meet_profile": (
                    minimum_variant_specific_mutations >= required_variant_mutations
                ),
                "pairwise_mutation_distance_meets_profile": (
                    minimum_pairwise_mutation_distance >= required_pairwise_distance
                ),
            }
        )
    if prompt_audit is not None:
        prompt_checks, prompt_observed = _constraint_prompt_admission(
            prompt_audit,
            minimum_counterfactual_flips=int(
                constraint_profile.get("minimum_counterfactual_flips", 2)
            ),
            expected_variants=set(scenario.variants),
        )
        checks.update(prompt_checks)
        observed.update(prompt_observed)
    if projection_witnesses is not None:
        projection_checks, projection_observed = _projection_witness_admission(
            projection_witnesses,
            expected_variants=set(scenario.variants),
            minimum_witnesses=int(
                constraint_profile.get("minimum_projection_witnesses", 1)
            ),
        )
        checks.update(projection_checks)
        observed.update(projection_observed)
    if scope_decision_profile:
        decision_payload = artifact_payloads["scope_decision_matrix"]
        try:
            decision_audit = analyze_scope_decision_matrix(decision_payload)
        except (TypeError, ValueError):
            checks["scope_decision_matrix_valid"] = False
        else:
            matrix_variants = {
                str(row.get("variant", ""))
                for row in decision_payload.get("rows", ())
                if isinstance(row, dict)
            }
            minimum_adaptive_depth = int(
                scope_decision_profile.get("minimum_adaptive_worst_case_depth", 2)
            )
            minimum_certificate = int(
                scope_decision_profile.get("minimum_static_certificate_size", 2)
            )
            observed.update(
                {
                    "scope_decision_variant_count": decision_audit.variant_count,
                    "scope_decision_signature_count": (
                        decision_audit.recovery_signature_count
                    ),
                    "scope_decision_surface_count": (
                        decision_audit.observable_surface_count
                    ),
                    "scope_decision_minimum_static_certificate_size": (
                        decision_audit.minimum_static_certificate_size or 0
                    ),
                    "scope_decision_optimal_adaptive_depth": (
                        decision_audit.optimal_adaptive_worst_case_depth or 0
                    ),
                    "scope_decision_single_surface_solver_count": len(
                        decision_audit.single_surface_solvers
                    ),
                }
            )
            checks.update(
                {
                    "scope_decision_matrix_valid": True,
                    "scope_decision_matrix_variants_exact": (
                        matrix_variants == expected_variants
                    ),
                    "scope_decision_scopes_identifiable": decision_audit.identifiable,
                    "scope_decision_static_certificate_meets_profile": (
                        decision_audit.minimum_static_certificate_size is not None
                        and decision_audit.minimum_static_certificate_size
                        >= minimum_certificate
                    ),
                    "scope_decision_adaptive_depth_meets_profile": (
                        decision_audit.optimal_adaptive_worst_case_depth is not None
                        and decision_audit.optimal_adaptive_worst_case_depth
                        >= minimum_adaptive_depth
                    ),
                    "scope_decision_has_no_single_surface_solver": (
                        not decision_audit.single_surface_solvers
                    ),
                }
            )
    if obligation_profile:
        interaction_payload = artifact_payloads["obligation_interactions"]
        try:
            interaction_audit = analyze_obligation_interactions(interaction_payload)
        except (TypeError, ValueError):
            checks["obligation_interaction_artifact_valid"] = False
        else:
            interaction_variants = {
                str(row.get("variant", ""))
                for row in interaction_payload.get("rows", ())
                if isinstance(row, dict)
            }
            required_obligations = int(
                obligation_profile.get("minimum_obligation_count", 5)
            )
            required_protected = int(
                obligation_profile.get("minimum_protected_obligation_count", 3)
            )
            required_scopes = int(
                obligation_profile.get("minimum_gold_scope_count", 3)
            )
            required_cross = int(
                obligation_profile.get("minimum_cross_obligation_witnesses", 3)
            )
            required_conflicts = int(
                obligation_profile.get(
                    "minimum_repair_preservation_conflict_witnesses", 2
                )
            )
            required_conflict_variants = int(
                obligation_profile.get("minimum_variants_with_conflict", 2)
            )
            observed.update(
                {
                    "obligation_count": interaction_audit.obligation_count,
                    "protected_obligation_count": (
                        interaction_audit.protected_obligation_count
                    ),
                    "obligation_action_count": interaction_audit.action_count,
                    "obligation_gold_scope_count": interaction_audit.gold_scope_count,
                    "obligation_probe_count": interaction_audit.probe_count,
                    "cross_obligation_witness_count": (
                        interaction_audit.cross_obligation_witness_count
                    ),
                    "repair_preservation_conflict_count": (
                        interaction_audit.repair_preservation_conflict_count
                    ),
                    "variants_with_cross_obligation_witness": (
                        interaction_audit.variants_with_cross_obligation_witness
                    ),
                    "variants_with_repair_preservation_conflict": (
                        interaction_audit.variants_with_repair_preservation_conflict
                    ),
                    "minimum_gold_action_count": (
                        interaction_audit.minimum_gold_action_count
                    ),
                }
            )
            checks.update(
                {
                    "obligation_interaction_artifact_valid": True,
                    "obligation_interaction_variants_exact": (
                        interaction_variants == expected_variants
                    ),
                    "obligation_interaction_probes_replay_bound": (
                        interaction_audit.replay_bound
                    ),
                    "obligation_count_meets_profile": (
                        interaction_audit.obligation_count >= required_obligations
                    ),
                    "protected_obligation_count_meets_profile": (
                        interaction_audit.protected_obligation_count
                        >= required_protected
                    ),
                    "obligation_gold_scopes_meet_profile": (
                        interaction_audit.gold_scope_count >= required_scopes
                    ),
                    "cross_obligation_witnesses_meet_profile": (
                        interaction_audit.cross_obligation_witness_count
                        >= required_cross
                    ),
                    "repair_preservation_conflicts_meet_profile": (
                        interaction_audit.repair_preservation_conflict_count
                        >= required_conflicts
                    ),
                    "conflict_variants_meet_profile": (
                        interaction_audit.variants_with_repair_preservation_conflict
                        >= required_conflict_variants
                    ),
                }
            )
    hard_passed = all(checks.values())
    requested_tier = scenario.tier
    candidate_passed = (
        all(value for name, value in checks.items() if name != "minimum_mutations>=4")
        and minimum_mutations >= 3
    )
    admitted_tier = (
        "hard" if hard_passed else "candidate" if candidate_passed else "easy"
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
        artifact_sha256={name: _sha256(path) for name, path in paths.items()},
    )
