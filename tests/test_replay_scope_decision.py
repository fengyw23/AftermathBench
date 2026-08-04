from __future__ import annotations

import unittest

from aftermath_bench.replay_scope_decision import audit_replayed_scope_decisions
from aftermath_bench.scope_decision_audit import analyze_scope_decision_matrix


class ReplayScopeDecisionTest(unittest.TestCase):
    def test_joined_observation_charges_both_public_query_surfaces(self) -> None:
        payload = {
            "rows": [
                {
                    "variant": "valid",
                    "recovery_signature": "preserve",
                    "observations": {
                        "package_inventory": ["binary"],
                        "content_matches_approval": True,
                    },
                },
                {
                    "variant": "corrupt",
                    "recovery_signature": "replace",
                    "observations": {
                        "package_inventory": ["binary"],
                        "content_matches_approval": False,
                    },
                },
            ],
            "surface_requirements": {
                "package_inventory": ["package_registry"],
                "content_matches_approval": [
                    "package_registry",
                    "approval_sources",
                ],
            },
        }
        audit = analyze_scope_decision_matrix(payload)
        self.assertEqual(audit.observable_surface_count, 2)
        self.assertEqual(audit.minimum_static_certificate_size, 2)
        self.assertEqual(audit.optimal_adaptive_worst_case_depth, 2)
        self.assertEqual(audit.single_surface_solvers, ())

    def test_linear_forgejo_stage_family_is_identifiable_but_too_shallow(self) -> None:
        stages = {
            "s1": ("absent", "absent", "absent", "absent", "absent"),
            "s2": ("waiting", "absent", "absent", "absent", "absent"),
            "s3": ("failure", "complete", "absent", "absent", "absent"),
            "s4": ("failure", "complete", "complete", "absent", "absent"),
            "s5": ("success", "complete", "complete", "accepted", "absent"),
            "s6": ("success", "complete", "complete", "accepted", "closed"),
        }
        reports = {
            variant: {
                "dimension_projection": dict(
                    zip(
                        (
                            "actions_owner",
                            "signed_bundle",
                            "production_deployment",
                            "external_attestation",
                            "release_metadata",
                        ),
                        values,
                        strict=True,
                    )
                )
            }
            for variant, values in stages.items()
        }
        scenario = {
            "scenario_id": "linear-promotion",
            "family": "forgejo-approved-artifact-promotion",
            "matched_variants": [
                {"id": variant, "recovery_signature_class": f"scope-{variant}"}
                for variant in stages
            ],
            "planned_admission_profile": {
                "scope_decision": {
                    "minimum_static_certificate_size": 4,
                    "minimum_adaptive_worst_case_depth": 4,
                }
            },
        }
        result = audit_replayed_scope_decisions(
            boundary_audit={"reports": reports}, scenario=scenario
        )
        self.assertTrue(result["checks"]["all_scopes_identifiable"])
        self.assertTrue(result["checks"]["no_single_surface_solver"])
        self.assertEqual(result["observed"]["minimum_static_certificate_size"], 3)
        self.assertEqual(result["observed"]["optimal_adaptive_worst_case_depth"], 2)
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
