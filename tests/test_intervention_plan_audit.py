from __future__ import annotations

import unittest

from aftermath_bench.intervention_plan_audit import (
    InterventionAction,
    audit_intervention_design,
)


OBLIGATIONS = frozenset({"actions", "registry", "production", "attestation", "metadata"})


class InterventionPlanAuditTest(unittest.TestCase):
    def test_rejects_one_gap_one_local_repair_star(self) -> None:
        actions = tuple(
            InterventionAction(
                name=f"repair_{name}",
                sets_true=frozenset({name}),
                unsafe_if_true=frozenset({name}),
            )
            for name in sorted(OBLIGATIONS)
        )
        variants = {"all_valid": OBLIGATIONS}
        variants.update(
            {
                f"{name}_missing": OBLIGATIONS - {name}
                for name in OBLIGATIONS
            }
        )
        report = audit_intervention_design(
            obligations=OBLIGATIONS,
            actions=actions,
            variants=variants,
        )
        self.assertFalse(report["passed_design_gate"])
        self.assertEqual(report["observed"]["multi_action_variant_count"], 0)
        self.assertEqual(report["observed"]["effect_overlap_pairs"], [])

    def test_accepts_composed_context_sensitive_interventions(self) -> None:
        actions = (
            InterventionAction(
                "materialize_bundle",
                frozenset({"actions"}),
                unsafe_if_true=frozenset({"actions"}),
            ),
            InterventionAction(
                "materialize_and_register",
                frozenset({"actions", "registry"}),
                unsafe_if_true=frozenset({"actions", "registry"}),
            ),
            InterventionAction(
                "register_only",
                frozenset({"registry"}),
                requires_true=frozenset({"actions"}),
                unsafe_if_true=frozenset({"registry"}),
            ),
            InterventionAction(
                "deploy_only",
                frozenset({"production"}),
                requires_true=frozenset({"registry"}),
                unsafe_if_true=frozenset({"production"}),
            ),
            InterventionAction(
                "deploy_and_attest",
                frozenset({"production", "attestation"}),
                requires_true=frozenset({"registry"}),
                unsafe_if_true=frozenset({"production", "attestation"}),
            ),
            InterventionAction(
                "attest_only",
                frozenset({"attestation"}),
                requires_true=frozenset({"production"}),
                unsafe_if_true=frozenset({"attestation"}),
            ),
            InterventionAction(
                "publish_metadata",
                frozenset({"metadata"}),
                requires_true=frozenset(
                    {"actions", "production", "attestation"}
                ),
                unsafe_if_true=frozenset({"metadata"}),
            ),
            InterventionAction(
                "deploy_attest_and_publish",
                frozenset({"production", "attestation", "metadata"}),
                requires_true=frozenset({"actions", "registry"}),
                unsafe_if_true=frozenset(
                    {"production", "attestation", "metadata"}
                ),
            ),
        )
        variants = {
            "all_valid": OBLIGATIONS,
            "actions_and_attestation_missing": OBLIGATIONS
            - {"actions", "attestation"},
            "registry_and_production_missing": OBLIGATIONS
            - {"registry", "production"},
            "registry_and_metadata_missing": OBLIGATIONS
            - {"registry", "metadata"},
            "actions_registry_metadata_missing": OBLIGATIONS
            - {"actions", "registry", "metadata"},
            "registry_production_attestation_missing": OBLIGATIONS
            - {"registry", "production", "attestation"},
            "actions_production_metadata_missing": OBLIGATIONS
            - {"actions", "production", "metadata"},
            "registry_and_all_downstream_missing": frozenset({"actions"}),
        }
        report = audit_intervention_design(
            obligations=OBLIGATIONS,
            actions=actions,
            variants=variants,
        )
        self.assertTrue(report["passed_design_gate"], report)
        self.assertGreaterEqual(
            report["observed"]["multi_action_variant_count"], 3
        )
        self.assertGreaterEqual(len(report["observed"]["effect_overlap_pairs"]), 2)
        self.assertGreaterEqual(
            report["observed"]["tempting_unsafe_choice_count"], 3
        )


if __name__ == "__main__":
    unittest.main()
