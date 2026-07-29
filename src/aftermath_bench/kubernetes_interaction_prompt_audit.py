from __future__ import annotations

import hashlib
import json
from itertools import combinations
from typing import Any

from .integrations.kubernetes_interaction_prefix import interaction_prefix_manifests
from .integrations.kubernetes_interaction_scope import derive_interaction_scope
from .native_kubernetes_interaction_family import (
    KUBERNETES_INTERACTION_FAMILY,
    KUBERNETES_INTERACTION_SYSTEM_PROMPT,
    kubernetes_interaction_initial_message,
)
from .native_scenario import NativeScenario


def _surface(surface_id: str, text: str) -> dict[str, str]:
    return {
        "id": surface_id,
        "text": text,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _manifest_data(name: str) -> str:
    document = next(
        item
        for item in interaction_prefix_manifests()
        if item.get("metadata", {}).get("name") == name
    )
    return json.dumps(document.get("data", {}), sort_keys=True, ensure_ascii=False)


def _tool_surface() -> str:
    return json.dumps(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
            for tool in KUBERNETES_INTERACTION_FAMILY.tool_definitions
        ],
        sort_keys=True,
        ensure_ascii=False,
    )


def build_interaction_prompt_audit(
    scenario: NativeScenario,
    *,
    variant_facts: dict[str, dict[str, Any]],
    prefix_trace: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    visible_failure: dict[str, Any],
    max_turns: int = 25,
) -> dict[str, Any]:
    ordinary_message = kubernetes_interaction_initial_message(
        scenario=scenario,
        prefix={"trace": list(prefix_trace)},
        failure_report={
            "variant": scenario.variants[0],
            "visible_failure": visible_failure,
        },
        execution_control=False,
    )
    contracts = {
        "schema": "schema-contract",
        "compatibility": "compatibility-contract",
        "credential": "credential-contract",
        "controller": "controller-contract",
        "publication": "publication-contract",
        "closure": "audit-contract",
    }
    surfaces = [
        _surface("ordinary_initial_message", ordinary_message),
        _surface("user_instruction", str(scenario.raw["user_instruction"])),
        _surface(
            "system_prompt",
            KUBERNETES_INTERACTION_SYSTEM_PROMPT.format(max_turns=max_turns),
        ),
        _surface(
            "known_identifiers",
            json.dumps(scenario.raw["fixture"], sort_keys=True, ensure_ascii=False),
        ),
        _surface(
            "successful_prior_tool_activity",
            json.dumps(prefix_trace, sort_keys=True, ensure_ascii=False),
        ),
        _surface(
            "latest_attempted_operation",
            str(scenario.raw["ambiguous_operation"]["operation"]),
        ),
        _surface(
            "latest_tool_result",
            json.dumps(visible_failure, sort_keys=True, ensure_ascii=False),
        ),
        _surface("tool_descriptions", _tool_surface()),
    ]
    surfaces.extend(
        _surface(f"{group}_contract", _manifest_data(name))
        for group, name in contracts.items()
    )
    group_surfaces = {
        "native_commit_and_consumers": ["schema_contract", "tool_descriptions"],
        "compatibility_and_batch": ["compatibility_contract", "tool_descriptions"],
        "shared_credential": ["credential_contract", "tool_descriptions"],
        "controller_ownership": ["controller_contract", "tool_descriptions"],
        "external_publication": ["publication_contract", "tool_descriptions"],
        "closure_records": ["closure_contract", "tool_descriptions"],
    }
    constraint_surfaces = {
        "epoch_monotonicity": ["schema_contract"],
        "consumer_compatibility": ["schema_contract", "compatibility_contract"],
        "non_replayable_batch_protection": ["compatibility_contract"],
        "credential_rotation_guard": ["credential_contract"],
        "owner_uniqueness": ["controller_contract"],
        "release_preconditions": [
            "publication_contract",
            "schema_contract",
            "credential_contract",
        ],
        "external_exactly_once": ["publication_contract"],
        "audit_closure": ["closure_contract"],
    }
    pairs = []
    for left, right in combinations(scenario.variants, 2):
        changed = sorted(
            key
            for key in set(variant_facts[left]) | set(variant_facts[right])
            if variant_facts[left].get(key) != variant_facts[right].get(key)
        )
        if len(changed) != 1:
            continue
        pairs.append(
            {
                "left": left,
                "right": right,
                "changed_fact_count": 1,
                "changed_facts": changed,
                "direction_flipped": (
                    derive_interaction_scope(variant_facts[left])
                    != derive_interaction_scope(variant_facts[right])
                ),
            }
        )
    all_groups = list(group_surfaces)
    all_constraints = list(constraint_surfaces)
    decisive_surfaces = sorted(
        {surface for values in group_surfaces.values() for surface in values}
    )
    return {
        "schema_version": "1.0",
        "scenario_id": scenario.scenario_id,
        "visible_surfaces": list(surfaces),
        "required_surface_ids": [surface["id"] for surface in surfaces],
        "forbidden_direction_labels": sorted(
            {
                derive_interaction_scope(facts)
                for facts in variant_facts.values()
            }
        ),
        "constraint_evidence_groups": [
            {"id": group, "surface_ids": source_ids}
            for group, source_ids in group_surfaces.items()
        ],
        "constraints": [
            {"id": constraint, "surface_ids": source_ids}
            for constraint, source_ids in constraint_surfaces.items()
        ],
        "variant_derivations": [
            {
                "variant": variant,
                "evidence_groups": all_groups,
                "constraint_ids": all_constraints,
                "decisive_surface_ids": decisive_surfaces,
            }
            for variant in scenario.variants
        ],
        "counterfactual_pairs": pairs,
        "variant_facts": variant_facts,
    }
