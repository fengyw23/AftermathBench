from __future__ import annotations

import json
import unittest
from pathlib import Path


class ERPNextHiddenTest003ReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.receipt = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "data"
                / "diagnostics"
                / "erpnext"
                / "manufacturing-hidden-test-003-30807548714.json"
            ).read_text(encoding="utf-8")
        )

    def test_receipt_binds_freeze_evaluation_and_public_artifact(self) -> None:
        self.assertEqual(self.receipt["lifecycle_status"], "consumed")
        self.assertEqual(self.receipt["freeze_provenance"]["run_id"], 30804648059)
        self.assertEqual(self.receipt["evaluation"]["run_id"], 30807548714)
        self.assertTrue(
            self.receipt["published_artifact"]["digest"].startswith("sha256:")
        )
        self.assertTrue(self.receipt["usage_ledger"]["integrity_passed"])
        self.assertEqual(
            self.receipt["usage_ledger"]["events"],
            ["frozen", "evaluation_locked", "consumed"],
        )

    def test_hidden_result_is_complete_and_has_no_infrastructure_errors(self) -> None:
        aggregate = self.receipt["evaluation"]["aggregate"]
        self.assertEqual(aggregate["completed_runs"], 4)
        self.assertEqual(aggregate["run_error_count"], 0)
        self.assertEqual(aggregate["task_pass_rate"], 0.75)
        self.assertEqual(aggregate["matched_group_success_rate"], 0.0)
        self.assertEqual(aggregate["component_pass_rates"]["protocol_safety"], 0.75)

    def test_public_receipt_does_not_claim_to_publish_hidden_state(self) -> None:
        privacy = self.receipt["privacy"]
        self.assertFalse(privacy["raw_hidden_bundle_published"])
        self.assertFalse(privacy["raw_model_trajectories_published"])
        self.assertTrue(privacy["encrypted_audit_published"])


if __name__ == "__main__":
    unittest.main()
