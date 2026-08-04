from __future__ import annotations

import copy
import unittest

from aftermath_bench.integrations.erpnext_inventory_cost_recovery import (
    project_inventory_cost_dimensions,
)


class InventoryCostSemanticProjectionTest(unittest.TestCase):
    @staticmethod
    def _evidence() -> dict:
        return {
            "landed_cost_voucher": {"docstatus": 1},
            "stock_ledger_entries": [
                {
                    "name": "SLE-RUNTIME-1",
                    "voucher_type": "Purchase Receipt",
                    "voucher_no": "PR-1",
                    "voucher_detail_no": "ROW-RUNTIME-1",
                    "actual_qty": 20,
                    "qty_after_transaction": 20,
                    "valuation_rate": 600,
                    "stock_value": 12000,
                    "stock_value_difference": 12000,
                    "is_cancelled": 0,
                    "item_code": "COMPONENT",
                    "warehouse": "Stores - AL",
                    "posting_date": "2026-08-04",
                    "posting_time": "09:00:00",
                }
            ],
            "gl_entries": [
                {
                    "name": "GL-RUNTIME-1",
                    "voucher_type": "Purchase Receipt",
                    "voucher_no": "PR-1",
                    "voucher_detail_no": "ROW-RUNTIME-1",
                    "debit": 12000,
                    "credit": 0,
                    "is_cancelled": 0,
                    "account": "Stock In Hand - AL",
                    "against": "Stock Received But Not Billed - AL",
                }
            ],
            "repost_item_valuations": [{"status": "Queued"}],
            "settlement_attestation": None,
            "rq_jobs": [{"status": "queued"}],
        }

    def test_runtime_ids_and_timestamps_do_not_create_false_state_variation(self) -> None:
        left = self._evidence()
        right = copy.deepcopy(left)
        right["stock_ledger_entries"][0].update(
            {
                "name": "SLE-RUNTIME-2",
                "voucher_detail_no": "ROW-RUNTIME-2",
                "posting_time": "09:04:59",
            }
        )
        right["gl_entries"][0].update(
            {"name": "GL-RUNTIME-2", "voucher_detail_no": "ROW-RUNTIME-2"}
        )
        self.assertEqual(
            project_inventory_cost_dimensions(left),
            project_inventory_cost_dimensions(right),
        )

    def test_business_value_change_alters_semantic_projection(self) -> None:
        left = self._evidence()
        right = copy.deepcopy(left)
        right["stock_ledger_entries"][0]["valuation_rate"] = 660
        right["gl_entries"][0]["debit"] = 13200
        left_projection = project_inventory_cost_dimensions(left)
        right_projection = project_inventory_cost_dimensions(right)
        self.assertNotEqual(
            left_projection["stock_ledger"], right_projection["stock_ledger"]
        )
        self.assertNotEqual(
            left_projection["gl_entries"], right_projection["gl_entries"]
        )


if __name__ == "__main__":
    unittest.main()
