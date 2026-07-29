from __future__ import annotations

import json
import unittest

from aftermath_bench.schema import repository_root


class ERPNextSalesReturnBlueprintTest(unittest.TestCase):
    def test_blueprint_is_explicitly_unvalidated(self) -> None:
        root = repository_root()
        scenario = json.loads(
            (
                root
                / "data"
                / "scenario_blueprints"
                / "erpnext-sales-return-dev-001"
                / "scenario.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(scenario["benchmark_tier"], "unvalidated")
        self.assertEqual(len(scenario["matched_variants"]), 4)
        self.assertNotIn("admission_artifacts", scenario)

    def test_source_audit_does_not_claim_execution_admission(self) -> None:
        audit = json.loads(
            (
                repository_root()
                / "data"
                / "runtimes"
                / "erpnext-v15"
                / "sales_return_source_audit.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            audit["runtime_revision"],
            "b9c9b76f5b043bd542b01dd4fefe913416a7bb53",
        )
        self.assertEqual(
            audit["status"],
            "source-audited-live-replay-pending",
        )
        self.assertGreaterEqual(len(audit["operations"]), 4)


if __name__ == "__main__":
    unittest.main()
