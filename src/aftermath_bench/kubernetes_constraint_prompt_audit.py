from __future__ import annotations

import hashlib
import json
from typing import Any

from .integrations.kubernetes_constraint_prefix import constraint_prefix_manifests
from .native_kubernetes_constraint_family import (
    KUBERNETES_CONSTRAINT_SYSTEM_PROMPT,
    KUBERNETES_MIGRATION_TOOL_DEFINITIONS,
)
from .native_scenario import NativeScenario

PAIR_DEFINITIONS = (
    (
        "failed_migration_without_preparation",
        "failed_migration_with_preparation",
    ),
    (
        "committed_cutover_without_publication",
        "committed_cutover_with_publication",
    ),
)


def _surface(surface_id: str, text: str) -> dict[str, str]:
    return {
        "id": surface_id,
        "text": text,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _manifest_data(name: str) -> str:
    document = next(
        item
        for item in constraint_prefix_manifests()
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
            for tool in KUBERNETES_MIGRATION_TOOL_DEFINITIONS
        ],
        sort_keys=True,
        ensure_ascii=False,
    )


def _changed_fact_count(left: dict[str, Any], right: dict[str, Any]) -> int:
    keys = set(left) | set(right)
    return sum(left.get(key) != right.get(key) for key in keys)


def build_constraint_prompt_audit(
    scenario: NativeScenario,
    *,
    variant_facts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    surfaces = (
        _surface("user_instruction", str(scenario.raw["user_instruction"])),
        _surface("system_prompt", KUBERNETES_CONSTRAINT_SYSTEM_PROMPT),
        _surface("tool_descriptions", _tool_surface()),
        _surface("change_authorization", _manifest_data("recovery-policy")),
        _surface("schema_contract", _manifest_data("schema-contract")),
        _surface("serving_contract", _manifest_data("serving-contract")),
        _surface("registry_contract", _manifest_data("registry-contract")),
        _surface("audit_contract", _manifest_data("audit-contract")),
    )
    derivation_groups = {
        "failed_migration_without_preparation": (
            "authorization",
            "catalog_job",
            "serving",
            "registry",
        ),
        "failed_migration_with_preparation": (
            "authorization",
            "catalog_job",
            "serving",
            "registry",
        ),
        "committed_cutover_without_publication": (
            "catalog_job",
            "serving",
            "registry",
            "closure",
        ),
        "committed_cutover_with_publication": (
            "catalog_job",
            "serving",
            "registry",
            "closure",
        ),
    }
    derivation_constraints = {
        "failed_migration_without_preparation": (
            "closed_window",
            "schema_monotonicity",
            "compatible_serving",
        ),
        "failed_migration_with_preparation": (
            "closed_window",
            "schema_monotonicity",
            "prepare_must_resolve",
        ),
        "committed_cutover_without_publication": (
            "schema_monotonicity",
            "compatible_serving",
            "release_requires_committed_cutover",
        ),
        "committed_cutover_with_publication": (
            "schema_monotonicity",
            "external_exactly_once",
            "audit_closure",
        ),
    }
    counterfactual_pairs = []
    for left, right in PAIR_DEFINITIONS:
        changed = _changed_fact_count(variant_facts[left], variant_facts[right])
        counterfactual_pairs.append(
            {
                "left": left,
                "right": right,
                "changed_fact_count": changed,
                "changed_facts": sorted(
                    key
                    for key in set(variant_facts[left]) | set(variant_facts[right])
                    if variant_facts[left].get(key) != variant_facts[right].get(key)
                ),
                "direction_flipped": True,
            }
        )
    return {
        "schema_version": "1.0",
        "scenario_id": scenario.scenario_id,
        "visible_surfaces": list(surfaces),
        "required_surface_ids": [surface["id"] for surface in surfaces],
        "forbidden_direction_labels": [
            "rollback_to_stable",
            "compensate_external_effect",
            "forward_complete",
            "repair_downstream_only",
            "discard_uncommitted_candidate",
            "compensate_then_discard_candidate",
            "publish_committed_cutover",
            "close_already_published_cutover",
        ],
        "constraint_evidence_groups": [
            {"id": "authorization", "surface_ids": ["change_authorization"]},
            {
                "id": "catalog_job",
                "surface_ids": ["schema_contract", "tool_descriptions"],
            },
            {"id": "serving", "surface_ids": ["serving_contract"]},
            {"id": "registry", "surface_ids": ["registry_contract"]},
            {"id": "closure", "surface_ids": ["audit_contract"]},
        ],
        "constraints": [
            {"id": "closed_window", "surface_ids": ["change_authorization"]},
            {"id": "schema_monotonicity", "surface_ids": ["schema_contract"]},
            {"id": "compatible_serving", "surface_ids": ["serving_contract"]},
            {"id": "prepare_must_resolve", "surface_ids": ["registry_contract"]},
            {
                "id": "release_requires_committed_cutover",
                "surface_ids": ["registry_contract", "schema_contract"],
            },
            {"id": "external_exactly_once", "surface_ids": ["registry_contract"]},
            {"id": "audit_closure", "surface_ids": ["audit_contract"]},
        ],
        "variant_derivations": [
            {
                "variant": variant,
                "evidence_groups": list(derivation_groups[variant]),
                "constraint_ids": list(derivation_constraints[variant]),
                "decisive_surface_ids": sorted(
                    {
                        surface
                        for group in derivation_groups[variant]
                        for surface in next(
                            item["surface_ids"]
                            for item in (
                                {
                                    "id": "authorization",
                                    "surface_ids": ["change_authorization"],
                                },
                                {
                                    "id": "catalog_job",
                                    "surface_ids": [
                                        "schema_contract",
                                        "tool_descriptions",
                                    ],
                                },
                                {"id": "serving", "surface_ids": ["serving_contract"]},
                                {
                                    "id": "registry",
                                    "surface_ids": ["registry_contract"],
                                },
                                {"id": "closure", "surface_ids": ["audit_contract"]},
                            )
                            if item["id"] == group
                        )
                    }
                ),
            }
            for variant in scenario.variants
        ],
        "counterfactual_pairs": counterfactual_pairs,
        "variant_facts": variant_facts,
    }
