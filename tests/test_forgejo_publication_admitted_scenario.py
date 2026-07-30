from __future__ import annotations

import json
import unittest

from aftermath_bench.native_admission import validate_native_scenario
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root


class ForgejoPublicationAdmittedScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = load_native_scenario(
            repository_root()
            / "data"
            / "scenarios"
            / "forgejo-release-publication-dev-002"
            / "scenario.json"
        )

    def test_archived_native_evidence_passes_hard_admission(self) -> None:
        report = validate_native_scenario(self.scenario)

        self.assertTrue(report.passed)
        self.assertEqual(report.admitted_tier, "hard")
        self.assertEqual(report.observed["successful_prefix_writes"], 21)
        self.assertEqual(report.observed["replayed_relation_count"], 30)
        self.assertEqual(
            report.observed["distinct_recovery_signature_count"],
            5,
        )
        self.assertEqual(report.observed["minimum_repair_mutations"], 4)
        self.assertEqual(report.observed["maximum_heuristic_pass_rate"], 0.25)

    def test_reference_and_fixed_policy_results_are_complete(self) -> None:
        reference = json.loads(
            self.scenario.resolve_artifact("reference").read_text(
                encoding="utf-8"
            )
        )
        baselines = json.loads(
            self.scenario.resolve_artifact("baselines").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(len(reference["reports"]), 8)
        self.assertTrue(
            all(report["passed"] for report in reference["reports"])
        )
        self.assertEqual(len(baselines["expected_variants"]), 8)
        self.assertEqual(baselines["matched_group_solvers"], [])
        self.assertEqual(baselines["maximum_heuristic_pass_rate"], 0.25)


if __name__ == "__main__":
    unittest.main()
