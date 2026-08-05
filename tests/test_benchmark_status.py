from __future__ import annotations

import unittest

from aftermath_bench.benchmark_status import build_benchmark_status
from aftermath_bench.cli import build_parser


class BenchmarkStatusTest(unittest.TestCase):
    def test_status_keeps_planned_and_implemented_counts_separate(self) -> None:
        report = build_benchmark_status()

        self.assertEqual(report["planned"]["target_case_count"], 183)
        self.assertTrue(report["planned"]["matrix_valid"])
        self.assertEqual(
            report["implemented"]["scenario_count"],
            len(report["scenarios"]),
        )
        covered = {
            (row["domain_id"], row["family_id"])
            for row in report["scenarios"]
            if row["family_in_target_matrix"]
        }
        self.assertEqual(
            report["implemented"]["unique_target_family_coverage_count"],
            len(covered),
        )
        self.assertEqual(
            report["implemented"]["missing_target_family_count"],
            report["planned"]["family_count"] - len(covered),
        )
        self.assertEqual(
            report["implemented"]["formal_release_scenario_count"],
            report["release_manifest"]["observed"][
                "formal_verified_slot_count"
            ],
        )
        self.assertEqual(report["release_state"], "partial_release")
        self.assertEqual(
            report["implemented"]["hard_development_candidate_count"], 0
        )
        self.assertEqual(
            report["implemented"]["hard_development_candidate_case_count"],
            0,
        )
        self.assertTrue(report["release_manifest"]["passed"])
        self.assertEqual(
            report["model_evidence"]["counts"][
                "active_hard_ordinary_unique_state_count"
            ],
            25,
        )
        self.assertEqual(
            report["model_evidence"]["counts"][
                "current_formal_model_tested_unique_state_count"
            ],
            0,
        )

    def test_status_reports_exact_target_slot_coverage(self) -> None:
        report = build_benchmark_status()
        coverage = report["slot_coverage"]

        self.assertEqual(coverage["required_slot_count"], 36)
        self.assertEqual(
            coverage["slot_state_counts"]["formal_bound"],
            report["implemented"]["formal_release_scenario_count"],
        )
        self.assertEqual(
            coverage["matched_case_state_counts"]["formal_bound"],
            report["implemented"]["formal_release_matched_case_count"],
        )
        self.assertEqual(
            report["implemented"]["target_slot_state_counts"],
            coverage["slot_state_counts"],
        )
        self.assertEqual(
            report["implemented"]["target_matched_case_state_counts"],
            coverage["matched_case_state_counts"],
        )
        self.assertGreaterEqual(
            coverage["slot_state_counts"]["frozen_hidden"],
            4,
        )
        self.assertGreaterEqual(
            coverage["matched_case_state_counts"]["frozen_hidden"],
            16,
        )
        self.assertEqual(
            report["implemented"]["frozen_hidden_slot_count"],
            coverage["slot_state_counts"]["frozen_hidden"],
        )
        self.assertEqual(
            report["implemented"]["frozen_hidden_matched_case_count"],
            coverage["matched_case_state_counts"]["frozen_hidden"],
        )
        self.assertEqual(
            sum(coverage["slot_state_counts"].values()),
            coverage["required_slot_count"],
        )
        by_id = {item["slot_id"]: item for item in coverage["slots"]}
        self.assertEqual(
            by_id[
                "kubernetes/k8s-constraint-interaction-recovery/dev-006"
            ]["state"],
            "formal_bound",
        )
        self.assertEqual(
            by_id[
                "kubernetes/k8s-constraint-interaction-recovery/test-001"
            ]["state"],
            "frozen_hidden",
        )
        self.assertEqual(
            by_id[
                "erpnext/erpnext-manufacturing-rework/test-001"
            ]["state"],
            "frozen_hidden",
        )
        self.assertEqual(
            by_id[
                "erpnext/erpnext-multiwarehouse-transfer/test-002"
            ]["state"],
            "frozen_hidden",
        )

    def test_status_is_derived_from_admission_and_runtime_evidence(self) -> None:
        report = build_benchmark_status()
        scenarios = {
            row["scenario_id"]: row for row in report["scenarios"]
        }

        self.assertEqual(
            scenarios["erpnext-sales-return-dev-001"]["admitted_tier"],
            "hard",
        )
        self.assertTrue(
            scenarios["erpnext-sales-return-dev-001"][
                "runtime_execution_admitted"
            ]
        )
        self.assertTrue(
            scenarios["erpnext-sales-return-public-dev-001-r1"][
                "runtime_execution_admitted"
            ]
        )
        self.assertTrue(
            scenarios["erpnext-sales-return-public-dev-001-r1"][
                "formal_slot_split_matches"
            ]
        )
        self.assertEqual(
            scenarios["erpnext-partial-return-dev-001"]["admitted_tier"],
            "easy",
        )
        self.assertTrue(
            scenarios["k8s-constraint-interactions-dev-005"][
                "runtime_execution_admitted"
            ]
        )
        self.assertEqual(
            scenarios["forgejo-pr-release-dev-001"]["admitted_tier"],
            "easy",
        )
        self.assertTrue(
            scenarios["forgejo-pr-release-dev-001"][
                "runtime_execution_admitted"
            ]
        )
        self.assertEqual(
            scenarios["forgejo-release-publication-dev-002"][
                "admitted_tier"
            ],
            "hard",
        )
        self.assertTrue(
            scenarios["forgejo-release-publication-dev-002"][
                "runtime_execution_admitted"
            ]
        )

    def test_cli_exposes_status_command(self) -> None:
        args = build_parser().parse_args(["status"])
        self.assertEqual(args.command, "status")

    def test_cli_exposes_strict_release_validation(self) -> None:
        args = build_parser().parse_args(
            ["validate-release", "--require-full"]
        )
        self.assertEqual(args.command, "validate-release")
        self.assertTrue(args.require_full)

    def test_cli_exposes_model_evidence_validation(self) -> None:
        args = build_parser().parse_args(["validate-model-evidence"])
        self.assertEqual(args.command, "validate-model-evidence")


if __name__ == "__main__":
    unittest.main()
