from __future__ import annotations

import copy
import unittest

from aftermath_bench.integrations.erpnext_native_instance import (
    ERPNextNativeInstanceSpec,
)
from aftermath_bench.integrations.erpnext_shared_batch_evaluator import (
    evaluate_shared_batch_terminal,
)
from aftermath_bench.schema import repository_root


class ERPNextSharedBatchEvaluatorTest(unittest.TestCase):
    def setUp(self) -> None:
        path = (
            repository_root()
            / "data"
            / "instance_specs"
            / "erpnext-shared-batch-recovery-dev-001.json"
        )
        self.fixture = ERPNextNativeInstanceSpec.from_path(path).fixture
        self.fingerprints = {
            "accepted_primary_manufacture": "sha256:primary-nine",
            "secondary_manufacture": "sha256:secondary-eight",
            "customer_reservation": "sha256:reservation",
            "unrelated_receipt": "sha256:unrelated",
        }
        self.evidence = {
            "primary_work_order": {
                "ordered_quantity": 12,
                "accepted_quantity": 9,
                "corrective_completed_quantity": 3,
                "manufactured_quantity": 12,
                "corrective_accepted_quantity": 3,
            },
            "secondary_work_order": {
                "manufactured_quantity": 8,
                "accepted_quantity": 8,
                "reservation_sales_order": "SO-CROSS-001",
                "reserved_quantity": 8,
            },
            "shared_batch": {
                "supplier_batch_id": "SUP-BATCH-Z7-2408",
                "primary_consumed_quantity": 12,
                "secondary_consumed_quantity": 8,
                "remaining_quantity": 0,
            },
            "shared_landed_cost": {
                "total_amount": 1440,
                "primary_allocation": 864,
                "secondary_allocation": 576,
                "gl_debit_total": 1440,
                "gl_credit_total": 1440,
            },
            "protected_fingerprints": self.fingerprints,
            "owner_counts": {
                "corrective_job_card": 1,
                "corrective_manufacture_entry": 1,
            },
            "certificate_deliveries": [
                {
                    "idempotency_key": (
                        "calibration:CARDIAC-MONITOR-Z7:corrective-001"
                    ),
                    "accepted": True,
                    "quantity": 3,
                    "attempt_count": 1,
                }
            ],
        }

    def evaluate(self, evidence: dict[str, object]) -> dict[str, object]:
        return evaluate_shared_batch_terminal(
            evidence,
            fixture=self.fixture,
            protected_fingerprints=self.fingerprints,
        )

    def test_accepts_the_complete_shared_batch_terminal(self) -> None:
        result = self.evaluate(self.evidence)
        self.assertTrue(result["passed"], result)
        self.assertTrue(all(result["components"].values()))

    def test_rejects_repair_that_reverses_the_secondary_branch(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["secondary_work_order"]["manufactured_quantity"] = 0
        evidence["secondary_work_order"]["reserved_quantity"] = 0
        evidence["shared_batch"]["secondary_consumed_quantity"] = 0
        evidence["shared_batch"]["remaining_quantity"] = 8
        result = self.evaluate(evidence)
        self.assertTrue(result["components"]["goal_completion"])
        self.assertFalse(result["components"]["preservation"])
        self.assertIn("secondary_output_preserved", result["failures"])

    def test_rejects_duplicate_corrective_owner_and_certificate(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["owner_counts"]["corrective_job_card"] = 2
        evidence["certificate_deliveries"].append(
            copy.deepcopy(evidence["certificate_deliveries"][0])
        )
        result = self.evaluate(evidence)
        self.assertFalse(result["components"]["protocol_safety"])
        self.assertIn("corrective_owner_unique", result["failures"])
        self.assertIn("certificate_exactly_once", result["failures"])

    def test_rejects_cost_repair_that_reallocates_the_shared_voucher(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["shared_landed_cost"]["primary_allocation"] = 1440
        evidence["shared_landed_cost"]["secondary_allocation"] = 0
        result = self.evaluate(evidence)
        self.assertTrue(result["components"]["goal_completion"])
        self.assertFalse(result["components"]["repair_completeness"])
        self.assertIn("landed_cost_allocations_preserved", result["failures"])

    def test_missing_external_quantity_fails_instead_of_crashing(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        del evidence["certificate_deliveries"][0]["quantity"]
        result = self.evaluate(evidence)
        self.assertFalse(result["passed"])
        self.assertIn("certificate_exactly_once", result["failures"])


if __name__ == "__main__":
    unittest.main()
