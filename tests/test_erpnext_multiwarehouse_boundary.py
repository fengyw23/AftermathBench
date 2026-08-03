from __future__ import annotations

import unittest

from scripts.run_erpnext_multiwarehouse_failure import (
    validate_multiwarehouse_boundary,
)


class ERPNextMultiwarehouseBoundaryTests(unittest.TestCase):
    def test_no_primary_effect_boundary_is_distinct(self) -> None:
        prefix = {
            "second_leg_stock_entry": "STE-IN",
            "outgoing_stock_entry": "STE-OUT",
            "clinic_sales_order": "SO-CLINIC",
            "transfer_item": "ITEM-A",
            "transfer_quantity": 12,
            "transit_warehouse": "Transit - AL",
            "destination_warehouse": "Destination - AL",
        }
        evidence = {
            "second_leg_stock_entries": [{"name": "STE-IN", "docstatus": 0}],
            "outgoing_stock_entry": {"name": "STE-OUT", "docstatus": 1},
            "protected_reservation": {"name": "SRE-P", "docstatus": 1},
            "stock_reservation_entries": [],
            "stock_ledger_entries": [],
            "rq_jobs": [],
            "arrival_deliveries": {"STE-IN": None},
        }
        events = [
            {
                "method": "POST",
                "path": "/api/method/frappe.client.submit",
                "outcome": "request_suppressed",
                "upstream_status": None,
            }
        ]
        result = validate_multiwarehouse_boundary(
            "request_not_reached", evidence, prefix, events
        )
        self.assertTrue(result["passed"], result["failures"])


if __name__ == "__main__":
    unittest.main()
