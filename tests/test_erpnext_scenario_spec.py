import json
import unittest
from pathlib import Path

from aftermath_bench.schema import repository_root


class ERPNextScenarioSpecTest(unittest.TestCase):
    def setUp(self) -> None:
        path = (
            repository_root()
            / "data"
            / "scenarios"
            / "erpnext-procurement-payment-001"
            / "scenario.json"
        )
        self.scenario = json.loads(path.read_text(encoding="utf-8"))

    def test_prefix_has_real_multi_document_commitments(self) -> None:
        self.assertGreaterEqual(len(self.scenario["successful_prefix"]), 6)
        operations = " ".join(
            step["operation"] for step in self.scenario["successful_prefix"]
        )
        for doctype in (
            "Purchase Order",
            "Purchase Receipt",
            "Purchase Invoice",
            "Payment Entry",
        ):
            self.assertIn(doctype, operations)

    def test_variants_use_native_boundaries_not_invented_partial_sql(self) -> None:
        variant_ids = {
            variant["id"] for variant in self.scenario["matched_variants"]
        }
        self.assertEqual(
            variant_ids,
            {
                "request_not_reached",
                "database_committed_response_lost",
                "after_commit_enqueue_failed",
                "async_job_pending",
            },
        )
        self.assertNotIn("partial_commit", variant_ids)

    def test_pending_scenario_cannot_be_mistaken_for_released_data(self) -> None:
        self.assertEqual(
            self.scenario["status"],
            "design_validated_runtime_pending",
        )
        self.assertGreaterEqual(len(self.scenario["admission_blockers"]), 3)


if __name__ == "__main__":
    unittest.main()
