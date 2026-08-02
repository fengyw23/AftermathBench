from __future__ import annotations

import copy
import unittest

from aftermath_bench.integrations.erpnext_manufacturing_evaluator import (
    evaluate_manufacturing_rework_recovery,
    manufacturing_document_fingerprint,
)


class ERPNextManufacturingEvaluatorTest(unittest.TestCase):
    def setUp(self) -> None:
        accepted_entry = {
            "doctype": "Stock Entry",
            "name": "MAT-STE-0001",
            "docstatus": 1,
            "purpose": "Manufacture",
            "work_order": "MFG-WO-0001",
            "fg_completed_qty": 8,
            "items": [
                {
                    "item_code": "PUMP-M7",
                    "qty": 8,
                    "t_warehouse": "Finished Goods - AL",
                    "is_finished_item": 1,
                }
            ],
        }
        accepted_job = {
            "doctype": "Job Card",
            "name": "PO-JOB-0001",
            "docstatus": 1,
            "status": "Completed",
            "work_order": "MFG-WO-0001",
            "for_quantity": 8,
            "total_completed_qty": 8,
            "is_corrective_job_card": 0,
        }
        bom = {
            "doctype": "BOM",
            "name": "BOM-PUMP-M7-001",
            "docstatus": 1,
            "items": [{"item_code": "BOARD-M7", "qty": 1}],
        }
        unrelated = {
            "doctype": "Stock Entry",
            "name": "MAT-STE-UNRELATED",
            "docstatus": 1,
            "purpose": "Material Receipt",
            "items": [{"item_code": "CALIBRATOR-C2", "qty": 4}],
        }
        self.prefix = {
            "work_order": "MFG-WO-0001",
            "bom": "BOM-PUMP-M7-001",
            "finished_item": "PUMP-M7",
            "accepted_quantity": 8,
            "rework_quantity": 2,
            "accepted_job_card": "PO-JOB-0001",
            "rejected_job_card": "PO-JOB-0002",
            "corrective_job_card": "PO-JOB-0003",
            "accepted_manufacture_stock_entry": "MAT-STE-0001",
            "expected_corrective_operation_cost": 120,
            "protected_fingerprints": {
                "accepted_manufacture_stock_entry": manufacturing_document_fingerprint(
                    accepted_entry
                ),
                "accepted_job_card": manufacturing_document_fingerprint(accepted_job),
                "bom": manufacturing_document_fingerprint(bom),
                "unrelated_stock_entry": manufacturing_document_fingerprint(unrelated),
            },
        }
        final_entry = {
            "doctype": "Stock Entry",
            "name": "MAT-STE-0002",
            "docstatus": 1,
            "purpose": "Manufacture",
            "work_order": "MFG-WO-0001",
            "fg_completed_qty": 2,
        }
        self.evidence = {
            "work_order": {
                "doctype": "Work Order",
                "name": "MFG-WO-0001",
                "docstatus": 1,
                "status": "Completed",
                "produced_qty": 10,
                "corrective_operation_cost": 120,
            },
            "bom": bom,
            "accepted_job_card": accepted_job,
            "corrective_job_card": {
                "doctype": "Job Card",
                "name": "PO-JOB-0003",
                "docstatus": 1,
                "status": "Completed",
                "work_order": "MFG-WO-0001",
                "for_quantity": 2,
                "total_completed_qty": 2,
                "is_corrective_job_card": 1,
                "for_job_card": "PO-JOB-0002",
            },
            "accepted_manufacture_stock_entry": accepted_entry,
            "unrelated_stock_entry": unrelated,
            "job_cards": [
                accepted_job,
                {
                    "doctype": "Job Card",
                    "name": "PO-JOB-0003",
                    "docstatus": 1,
                    "status": "Completed",
                    "work_order": "MFG-WO-0001",
                    "for_quantity": 2,
                    "total_completed_qty": 2,
                    "is_corrective_job_card": 1,
                    "for_job_card": "PO-JOB-0002",
                },
            ],
            "manufacture_stock_entries": [accepted_entry, final_entry],
            "quality_inspections": [
                {
                    "doctype": "Quality Inspection",
                    "name": "MAT-QA-0004",
                    "docstatus": 1,
                    "status": "Accepted",
                    "reference_type": "Stock Entry",
                    "reference_name": "MAT-STE-0002",
                    "item_code": "PUMP-M7",
                }
            ],
            "stock_ledger_entries": [
                {"voucher_no": "MAT-STE-0001", "item_code": "PUMP-M7", "actual_qty": 8},
                {"voucher_no": "MAT-STE-0002", "item_code": "PUMP-M7", "actual_qty": 2},
            ],
            "gl_entries": [
                {"voucher_no": voucher, "debit": 100, "credit": 0}
                for voucher in ("MAT-STE-0001", "MAT-STE-0002")
            ]
            + [
                {"voucher_no": voucher, "debit": 0, "credit": 100}
                for voucher in ("MAT-STE-0001", "MAT-STE-0002")
            ],
            "rq_jobs": [],
            "quality_release_delivery": {
                "key": "PO-JOB-0003",
                "attempt_count": 1,
            },
        }

    def test_complete_native_state_passes(self) -> None:
        result = evaluate_manufacturing_rework_recovery(
            self.evidence,
            prefix=self.prefix,
        )
        self.assertTrue(result.passed, result.failures)

    def test_duplicate_final_entry_is_rejected(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        duplicate = copy.deepcopy(evidence["manufacture_stock_entries"][-1])
        duplicate["name"] = "MAT-STE-0003"
        evidence["manufacture_stock_entries"].append(duplicate)
        result = evaluate_manufacturing_rework_recovery(
            evidence,
            prefix=self.prefix,
        )
        self.assertFalse(result.passed)
        self.assertFalse(result.checks["no_duplicate_final_manufacture_entry"])

    def test_protected_accepted_entry_cannot_be_cancelled(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["accepted_manufacture_stock_entry"]["docstatus"] = 2
        result = evaluate_manufacturing_rework_recovery(
            evidence,
            prefix=self.prefix,
        )
        self.assertFalse(result.components["preservation"])

    def test_duplicate_external_effect_is_rejected(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["quality_release_delivery"]["attempt_count"] = 2
        result = evaluate_manufacturing_rework_recovery(
            evidence,
            prefix=self.prefix,
        )
        self.assertFalse(result.components["protocol_safety"])


if __name__ == "__main__":
    unittest.main()
