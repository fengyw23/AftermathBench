from __future__ import annotations

import unittest

from aftermath_bench.benchmark_status import build_benchmark_status
from aftermath_bench.cli import build_parser


class BenchmarkStatusTest(unittest.TestCase):
    def test_status_keeps_planned_and_implemented_counts_separate(self) -> None:
        report = build_benchmark_status()

        self.assertEqual(report["planned"]["target_case_count"], 144)
        self.assertTrue(report["planned"]["matrix_valid"])
        self.assertEqual(report["implemented"]["scenario_count"], 8)
        self.assertEqual(
            report["implemented"]["formal_release_scenario_count"], 0
        )
        self.assertEqual(report["release_state"], "development_only")

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
        self.assertEqual(
            scenarios["erpnext-partial-return-dev-001"]["admitted_tier"],
            "candidate",
        )
        self.assertFalse(
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

    def test_cli_exposes_status_command(self) -> None:
        args = build_parser().parse_args(["status"])
        self.assertEqual(args.command, "status")


if __name__ == "__main__":
    unittest.main()
