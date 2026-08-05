from __future__ import annotations

import unittest
from pathlib import Path

from aftermath_bench.data_lineage import (
    DATASET_KIND,
    build_data_lineage_audit,
)
from aftermath_bench.strict_json import load_json_strict


ROOT = Path(__file__).resolve().parents[1]


class DataLineageAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = build_data_lineage_audit(ROOT)

    def test_audit_reports_current_repository_facts(self) -> None:
        summary = self.report["summary"]
        self.assertTrue(self.report["audit_completed"])
        self.assertEqual(self.report["dataset_characterization"], DATASET_KIND)
        self.assertEqual(summary["active_runtime_count"], 3)
        self.assertEqual(summary["active_scenario_count"], 21)
        self.assertEqual(summary["matched_state_count"], 110)
        self.assertEqual(summary["current_schema_scenario_count"], 19)
        self.assertEqual(summary["hard_admission_report_scenario_count"], 17)
        self.assertEqual(summary["native_replay_chain_verified_scenario_count"], 18)

    def test_checked_in_report_matches_recomputation(self) -> None:
        checked_in = load_json_strict(ROOT / "data/data_lineage_audit.json")
        self.assertEqual(checked_in, self.report)

    def test_native_and_semantic_provenance_are_not_conflated(self) -> None:
        summary = self.report["summary"]
        self.assertGreater(summary["native_replay_chain_verified_scenario_count"], 0)
        self.assertEqual(summary["business_basis_declared_scenario_count"], 0)
        self.assertEqual(summary["authorship_split_declared_scenario_count"], 0)
        self.assertEqual(summary["generator_bound_scenario_count"], 0)
        self.assertEqual(summary["generation_run_bound_scenario_count"], 0)
        self.assertEqual(summary["parameter_sources_declared_scenario_count"], 0)
        self.assertEqual(summary["publication_lineage_complete_scenario_count"], 0)
        self.assertEqual(self.report["reliability"]["overall"], "partial")

    def test_duplicate_json_key_is_not_silently_accepted(self) -> None:
        publication = next(
            row
            for row in self.report["scenarios"]
            if row["scenario_id"] == "forgejo-release-publication-dev-002"
        )
        self.assertFalse(
            publication["checks"]["native_generation"][
                "all_declared_artifacts_strict_json"
            ]
        )
        self.assertIn("artifact_not_strict_json", publication["caveats"])

    def test_audit_does_not_read_frozen_hidden_data(self) -> None:
        self.assertIn("frozen hidden data is not read", self.report["audit_scope"])
        self.assertTrue(
            all("hidden_test" not in row["benchmark_split"] for row in self.report["scenarios"])
        )
        self.assertTrue(
            all("hidden" not in row["scenario_path"] for row in self.report["scenarios"])
        )

    def test_active_runtimes_have_pinned_source_and_execution_evidence(self) -> None:
        self.assertEqual(len(self.report["runtimes"]), 3)
        for runtime in self.report["runtimes"]:
            self.assertTrue(runtime["source_audit_passed"])
            self.assertTrue(runtime["execution_admitted"])
            self.assertTrue(runtime["upstream_components"])
            self.assertTrue(
                all(component["revision"] for component in runtime["upstream_components"])
            )


if __name__ == "__main__":
    unittest.main()
