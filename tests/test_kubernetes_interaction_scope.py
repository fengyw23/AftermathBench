from __future__ import annotations

import unittest
import json

from aftermath_bench.integrations.kubernetes_interaction_scope import (
    INTERACTION_FACT_GROUPS,
    INTERACTION_VARIANT_FACTS,
    KUBERNETES_INTERACTION_VARIANTS,
    derive_interaction_scope,
    interaction_projection_report,
)
from aftermath_bench.schema import repository_root


class KubernetesInteractionScopeTest(unittest.TestCase):
    def test_blueprint_matches_implemented_matrix_and_projection_gate(self) -> None:
        path = (
            repository_root()
            / "data"
            / "scenario_blueprints"
            / "k8s-constraint-interactions-dev-005"
            / "scenario.json"
        )
        blueprint = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            [item["id"] for item in blueprint["matched_variants"]],
            list(KUBERNETES_INTERACTION_VARIANTS),
        )
        profile = blueprint["admission_profile"]["constraint_derived_scope"]
        self.assertTrue(profile["require_projection_witnesses"])
        self.assertEqual(
            profile["minimum_projection_witnesses"],
            len(INTERACTION_FACT_GROUPS),
        )

    def test_matrix_has_neutral_ids_and_many_semantic_scopes(self) -> None:
        self.assertGreaterEqual(len(KUBERNETES_INTERACTION_VARIANTS), 8)
        self.assertTrue(all(name.startswith("state_") for name in KUBERNETES_INTERACTION_VARIANTS))
        scopes = {
            derive_interaction_scope(facts)
            for facts in INTERACTION_VARIANT_FACTS.values()
        }
        self.assertGreaterEqual(len(scopes), 8)

    def test_every_declared_group_has_a_projection_witness(self) -> None:
        report = interaction_projection_report()
        self.assertTrue(report["all_declared_groups_have_witnesses"], report)
        self.assertEqual(
            report["projection_witness_count"],
            len(INTERACTION_FACT_GROUPS),
        )

    def test_epoch_and_external_keys_do_not_form_a_complete_tree(self) -> None:
        compact: dict[tuple[object, ...], set[str]] = {}
        for variant, facts in INTERACTION_VARIANT_FACTS.items():
            key = (
                facts["schema_epoch"],
                facts["preparation_present"],
                facts["release_accepted"],
            )
            compact.setdefault(key, set()).add(derive_interaction_scope(facts))
        self.assertTrue(any(len(scopes) > 1 for scopes in compact.values()))

    def test_single_fact_pairs_flip_scope(self) -> None:
        expected_pairs = {
            ("state_01", "state_02"),
            ("state_03", "state_04"),
            ("state_04", "state_05"),
            ("state_04", "state_06"),
            ("state_07", "state_08"),
            ("state_09", "state_10"),
            ("state_07", "state_11"),
            ("state_12", "state_13"),
            ("state_07", "state_13"),
        }
        for left, right in expected_pairs:
            left_facts = INTERACTION_VARIANT_FACTS[left]
            right_facts = INTERACTION_VARIANT_FACTS[right]
            changed = {
                key for key in left_facts if left_facts[key] != right_facts[key]
            }
            self.assertEqual(len(changed), 1, (left, right, changed))
            self.assertNotEqual(
                derive_interaction_scope(left_facts),
                derive_interaction_scope(right_facts),
            )


if __name__ == "__main__":
    unittest.main()
