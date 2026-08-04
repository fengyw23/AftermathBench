from __future__ import annotations

import unittest

from aftermath_bench.integrations.forgejo_reconciliation_faults import (
    FORGEJO_RECONCILIATION_VARIANTS,
    reconciliation_scope_matrix,
)
from aftermath_bench.scope_decision_audit import analyze_scope_decision_matrix


class ForgejoReconciliationFaultsTest(unittest.TestCase):
    def test_every_missing_effect_has_a_distinct_targeted_repair(self) -> None:
        variants = tuple(FORGEJO_RECONCILIATION_VARIANTS.values())
        missing = [item.missing_obligation for item in variants]
        scopes = [item.recovery_kind for item in variants]
        self.assertEqual(len(variants), 6)
        self.assertEqual(len(set(missing)), 6)
        self.assertEqual(len(set(scopes)), 6)

    def test_workflow_repairs_do_not_replay_later_valid_effects(self) -> None:
        variants = FORGEJO_RECONCILIATION_VARIANTS
        self.assertEqual(
            variants["actions_bundle_missing"].recovery_workflow_inputs,
            {"resume_stage": "start", "stop_after": "artifact"},
        )
        self.assertEqual(
            variants["artifact_registry_missing"].recovery_workflow_inputs,
            {"resume_stage": "after_artifact", "stop_after": "bundle"},
        )
        self.assertEqual(
            variants["production_deployment_missing"].recovery_workflow_inputs,
            {"resume_stage": "after_bundle", "stop_after": "deployment"},
        )
        self.assertEqual(
            variants["external_attestation_missing"].recovery_workflow_inputs,
            {"resume_stage": "after_deployment", "stop_after": "none"},
        )

    def test_design_requires_all_six_public_query_surfaces(self) -> None:
        audit = analyze_scope_decision_matrix(reconciliation_scope_matrix())
        self.assertEqual(audit.minimum_static_certificate_size, 6)
        self.assertEqual(audit.optimal_adaptive_worst_case_depth, 6)
        self.assertFalse(audit.single_surface_solvers)


if __name__ == "__main__":
    unittest.main()
