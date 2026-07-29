from __future__ import annotations

import unittest

from aftermath_bench.kubernetes_constraint_analysis import (
    analyze_kubernetes_constraint_report,
)


def _call(tool_name: str, **arguments: str) -> dict[str, object]:
    return {"name": tool_name, "arguments": arguments}


class KubernetesConstraintAnalysisTest(unittest.TestCase):
    def test_candidate_cleanup_omission_is_scope_failure_with_investigation_gap(self) -> None:
        report = {
            "variant": "failed_migration_without_preparation",
            "turns": [
                {
                    "tool_calls": [
                        _call("list_objects", resource="configmaps"),
                        _call("list_objects", resource="jobs"),
                        _call("list_objects", resource="deployments"),
                        _call("list_objects", resource="services"),
                        _call("list_external_deliveries"),
                    ]
                },
                {
                    "tool_calls": [
                        _call("patch_object", resource="configmaps", name="release-ledger")
                    ]
                },
            ],
            "final_evidence": {
                "boundary_facts": {"external_keys": ["release:orders-v1"]},
                "external_deliveries": [{"key": "release:orders-v1"}],
            },
            "evaluation": {
                "passed": False,
                "components": {
                    "goal_completion": False,
                    "repair_completeness": True,
                    "preservation": True,
                    "protocol_safety": True,
                },
                "checks": {"candidate_lifecycle_matches_commit_state": False},
                "diagnostics": {
                    "semantic_recovery_direction": "discard_uncommitted_candidate"
                },
            },
            "trajectory_diagnostics": {"primary_error": "state_inference_failure"},
        }
        row = analyze_kubernetes_constraint_report(report)
        self.assertEqual(row["refined_failure_type"], "scope_failure")
        self.assertEqual(
            row["failure_chain"],
            ["investigation_failure", "scope_failure"],
        )
        self.assertFalse(row["pre_mutation_facets"]["candidate_secret"])

    def test_reads_batched_with_first_write_do_not_count_as_prior_evidence(self) -> None:
        report = {
            "variant": "committed_cutover_without_publication",
            "turns": [
                {
                    "tool_calls": [
                        _call("get_object", resource="configmaps", name="database-catalog"),
                        _call("patch_object", resource="configmaps", name="release-ledger"),
                    ]
                }
            ],
            "final_evidence": {
                "boundary_facts": {"external_keys": ["release:orders-v1"]},
                "external_deliveries": [{"key": "release:orders-v1"}],
            },
            "evaluation": {
                "passed": False,
                "checks": {"repair": False},
                "diagnostics": {
                    "semantic_recovery_direction": "publish_committed_cutover"
                },
            },
            "trajectory_diagnostics": {"primary_error": "execution_failure"},
        }
        row = analyze_kubernetes_constraint_report(report)
        self.assertEqual(row["first_mutation_turn"], 1)
        self.assertFalse(row["pre_mutation_facets"]["catalog"])

    def test_detects_boundary_expanding_external_effect(self) -> None:
        report = {
            "variant": "committed_cutover_without_publication",
            "turns": [],
            "final_evidence": {
                "boundary_facts": {"external_keys": ["release:orders-v1"]},
                "external_deliveries": [
                    {"key": "release:orders-v1"},
                    {"key": "prepare:orders-v2"},
                    {"key": "release:orders-v2"},
                    {"key": "audit:recovery:orders-v2"},
                ],
            },
            "evaluation": {
                "passed": False,
                "components": {
                    "goal_completion": True,
                    "repair_completeness": False,
                    "preservation": True,
                    "protocol_safety": False,
                },
                "checks": {"no_unrequired_external_effects": False},
                "diagnostics": {
                    "semantic_recovery_direction": "publish_committed_cutover"
                },
            },
            "trajectory_diagnostics": {"primary_error": "scope_failure"},
        }
        row = analyze_kubernetes_constraint_report(report)
        self.assertEqual(row["unexpected_external_keys"], ["prepare:orders-v2"])
        self.assertFalse(row["boundary_relative_integrity"])

    def test_fact_projection_mismatch_is_state_inference_not_tool_execution(self) -> None:
        report = {
            "variant": "failed_migration_without_preparation",
            "turns": [
                {
                    "tool_calls": [
                        _call("list_objects", resource="configmaps"),
                        _call("list_objects", resource="jobs"),
                        _call("list_objects", resource="deployments"),
                        _call("list_objects", resource="secrets"),
                        _call("list_objects", resource="services"),
                        _call("list_external_deliveries"),
                    ]
                },
                {
                    "tool_calls": [
                        _call(
                            "patch_object",
                            resource="configmaps",
                            name="recovery-audit",
                        )
                    ]
                },
            ],
            "final_evidence": {
                "boundary_facts": {"external_keys": ["release:orders-v1"]},
                "external_deliveries": [{"key": "release:orders-v1"}],
            },
            "evaluation": {
                "passed": False,
                "components": {
                    "goal_completion": True,
                    "repair_completeness": False,
                    "preservation": True,
                    "protocol_safety": True,
                },
                "checks": {
                    "audit_records_observed_facts": False,
                    "closure_event_records_observed_facts": False,
                },
                "diagnostics": {
                    "semantic_recovery_direction": "discard_uncommitted_candidate"
                },
            },
            "trajectory_diagnostics": {"primary_error": "execution_failure"},
        }
        row = analyze_kubernetes_constraint_report(report)
        self.assertTrue(row["pre_mutation_full_reconstruction"])
        self.assertEqual(row["refined_failure_type"], "state_inference_failure")


if __name__ == "__main__":
    unittest.main()
