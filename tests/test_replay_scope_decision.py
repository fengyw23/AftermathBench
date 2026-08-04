from __future__ import annotations

import unittest

from aftermath_bench.replay_scope_decision import audit_replayed_scope_decisions


class ReplayScopeDecisionTest(unittest.TestCase):
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
