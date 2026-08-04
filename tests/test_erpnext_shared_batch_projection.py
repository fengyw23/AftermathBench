from __future__ import annotations

import unittest

from aftermath_bench.integrations.erpnext_shared_batch_projection import (
    project_shared_batch_terminal,
)


class ERPNextSharedBatchProjectionTest(unittest.TestCase):
    def test_projects_branch_allocations_and_consumption_from_native_records(
        self,
    ) -> None:
        prefix = {
            "primary_work_order": "WO-P",
            "secondary_work_order": "WO-S",
            "accepted_primary_manufacture": "STE-P9",
            "primary_purchase_receipt_item": "PRI-P",
            "secondary_purchase_receipt_item": "PRI-S",
            "shared_purchase_receipt": "PR-1",
            "rejected_primary_job_card": "JC-R",
        }
        fixture = {
            "primary_work_order": {"item_code": "FG-P"},
            "secondary_work_order": {"item_code": "FG-S"},
            "shared_component": {"item_code": "RAW"},
        }
        raw = {
            "shared_purchase_receipt": {
                "doctype": "Purchase Receipt",
                "name": "PR-1",
            },
            "primary_bom": {"doctype": "BOM", "name": "BOM-P"},
            "secondary_bom": {"doctype": "BOM", "name": "BOM-S"},
            "primary_transfer": {"doctype": "Stock Entry", "name": "STE-TP"},
            "secondary_transfer": {"doctype": "Stock Entry", "name": "STE-TS"},
            "primary_material_quality_inspection": {
                "doctype": "Quality Inspection",
                "name": "QI-MP",
            },
            "secondary_material_quality_inspection": {
                "doctype": "Quality Inspection",
                "name": "QI-MS",
            },
            "accepted_primary_job_card": {"doctype": "Job Card", "name": "JC-A"},
            "rejected_primary_job_card": {"doctype": "Job Card", "name": "JC-R"},
            "secondary_job_card": {"doctype": "Job Card", "name": "JC-S"},
            "accepted_primary_quality_inspection": {
                "doctype": "Quality Inspection",
                "name": "QI-A",
            },
            "rejected_quality_inspection": {
                "doctype": "Quality Inspection",
                "name": "QI-R",
            },
            "secondary_quality_inspection": {
                "doctype": "Quality Inspection",
                "name": "QI-S",
            },
            "primary_work_order": {"qty": 12, "produced_qty": 12},
            "secondary_work_order": {"qty": 8, "produced_qty": 8},
            "corrective_job_card": {
                "name": "JC-C",
                "docstatus": 1,
                "total_completed_qty": 3,
            },
            "stock_reservation_entry": {
                "docstatus": 1,
                "voucher_no": "SO-CROSS-001",
                "reserved_qty": 8,
            },
            "manufacture_stock_entries": [
                {
                    "name": "STE-P9",
                    "work_order": "WO-P",
                    "purpose": "Manufacture",
                    "docstatus": 1,
                },
                {
                    "name": "STE-P3",
                    "work_order": "WO-P",
                    "purpose": "Manufacture",
                    "docstatus": 1,
                },
                {
                    "name": "STE-S8",
                    "work_order": "WO-S",
                    "purpose": "Manufacture",
                    "docstatus": 1,
                },
            ],
            "stock_ledger_entries": [
                {"voucher_no": "STE-P9", "item_code": "RAW", "actual_qty": -9},
                {"voucher_no": "STE-P9", "item_code": "FG-P", "actual_qty": 9},
                {"voucher_no": "STE-P3", "item_code": "RAW", "actual_qty": -3},
                {"voucher_no": "STE-P3", "item_code": "FG-P", "actual_qty": 3},
                {"voucher_no": "STE-S8", "item_code": "RAW", "actual_qty": -8},
                {"voucher_no": "STE-S8", "item_code": "FG-S", "actual_qty": 8},
            ],
            "quality_inspections": [
                {
                    "docstatus": 1,
                    "status": "Accepted",
                    "reference_type": "Stock Entry",
                    "reference_name": "STE-P3",
                    "item_code": "FG-P",
                    "sample_size": 3,
                }
            ],
            "shared_landed_cost_voucher": {
                "doctype": "Landed Cost Voucher",
                "name": "LCV-1",
                "docstatus": 1,
                "total_taxes_and_charges": 1440,
                "items": [
                    {"purchase_receipt_item": "PRI-P", "applicable_charges": 864},
                    {"purchase_receipt_item": "PRI-S", "applicable_charges": 576},
                ],
            },
            "gl_entries": [
                {"voucher_no": "PR-1", "debit": 7140, "credit": 0},
                {"voucher_no": "PR-1", "debit": 0, "credit": 7140},
            ],
            "supplier_batch": {"batch_id": "BATCH-1", "batch_qty": 0},
            "accepted_primary_manufacture": {
                "doctype": "Stock Entry",
                "name": "STE-P9",
            },
            "secondary_manufacture": {"doctype": "Stock Entry", "name": "STE-S8"},
            "customer_reservation": {"doctype": "Sales Order", "name": "SO-CROSS-001"},
            "unrelated_receipt": {"doctype": "Stock Entry", "name": "STE-U"},
            "job_cards": [
                {
                    "name": "JC-C",
                    "docstatus": 1,
                    "is_corrective_job_card": 1,
                    "for_job_card": "JC-R",
                }
            ],
            "certificate_delivery": {
                "key": "cert-1",
                "payload": {"quantity": 3},
                "attempt_count": 1,
            },
        }
        projected = project_shared_batch_terminal(raw, prefix=prefix, fixture=fixture)
        self.assertEqual(projected["shared_batch"]["primary_consumed_quantity"], 12)
        self.assertEqual(projected["shared_batch"]["secondary_consumed_quantity"], 8)
        self.assertTrue(projected["secondary_work_order"]["reservation_active"])
        self.assertEqual(projected["shared_landed_cost"]["primary_allocation"], 864)
        self.assertEqual(projected["shared_landed_cost"]["secondary_allocation"], 576)
        self.assertEqual(projected["owner_counts"]["corrective_manufacture_entry"], 1)
        self.assertEqual(
            projected["primary_work_order"]["corrective_accepted_quantity"], 3
        )
        self.assertEqual(projected["certificate_deliveries"][0]["quantity"], 3)


if __name__ == "__main__":
    unittest.main()
