from __future__ import annotations

import copy
import unittest

from aftermath_bench.integrations.erpnext_multiwarehouse_evaluator import (
    evaluate_multiwarehouse_recovery,
    multiwarehouse_document_fingerprint,
)


class ERPNextMultiwarehouseEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        outgoing = {
            "doctype": "Stock Entry",
            "name": "MAT-STE-OUT-001",
            "docstatus": 1,
            "purpose": "Material Transfer",
            "stock_entry_type": "Material Transfer",
            "add_to_transit": 1,
            "per_transferred": 100,
            "items": [
                {
                    "item_code": "CLINIC-GATEWAY-X12",
                    "qty": 12,
                    "s_warehouse": "East Distribution - AL",
                    "t_warehouse": "Inter-Warehouse Transit - AL",
                    "batch_no": "GW-X12-2026-08-A",
                }
            ],
        }
        protected_reservation = {
            "doctype": "Stock Reservation Entry",
            "name": "SRE-PROTECTED-001",
            "docstatus": 1,
            "status": "Reserved",
            "item_code": "EMERGENCY-ROUTER-R4",
            "warehouse": "North Emergency - AL",
            "voucher_type": "Sales Order",
            "voucher_no": "SO-NORTH-001",
            "voucher_detail_no": "SO-ITEM-NORTH-001",
            "voucher_qty": 3,
            "reserved_qty": 3,
            "company": "Aftermath Laboratories LLC",
        }
        second_leg = {
            "doctype": "Stock Entry",
            "name": "MAT-STE-IN-001",
            "docstatus": 1,
            "purpose": "Material Transfer",
            "stock_entry_type": "Material Transfer",
            "outgoing_stock_entry": "MAT-STE-OUT-001",
            "items": [
                {
                    "item_code": "CLINIC-GATEWAY-X12",
                    "qty": 12,
                    "s_warehouse": "Inter-Warehouse Transit - AL",
                    "t_warehouse": "West Clinic - AL",
                    "batch_no": "GW-X12-2026-08-A",
                    "against_stock_entry": "MAT-STE-OUT-001",
                }
            ],
        }
        self.prefix = {
            "transfer_item": "CLINIC-GATEWAY-X12",
            "transfer_quantity": 12,
            "batch_id": "GW-X12-2026-08-A",
            "outgoing_stock_entry": "MAT-STE-OUT-001",
            "clinic_sales_order": "SO-CLINIC-001",
            "clinic_reserved_quantity": 4,
            "transit_warehouse": "Inter-Warehouse Transit - AL",
            "destination_warehouse": "West Clinic - AL",
            "protected_item": "EMERGENCY-ROUTER-R4",
            "protected_warehouse": "North Emergency - AL",
            "protected_stock_balance": 9,
            "protected_fingerprints": {
                "outgoing_stock_entry": multiwarehouse_document_fingerprint(outgoing),
                "protected_reservation": multiwarehouse_document_fingerprint(
                    protected_reservation
                ),
            },
        }
        self.evidence = {
            "outgoing_stock_entry": outgoing,
            "second_leg_stock_entries": [second_leg],
            "stock_reservation_entries": [
                protected_reservation,
                {
                    "doctype": "Stock Reservation Entry",
                    "name": "SRE-CLINIC-001",
                    "docstatus": 1,
                    "status": "Reserved",
                    "item_code": "CLINIC-GATEWAY-X12",
                    "warehouse": "West Clinic - AL",
                    "voucher_type": "Sales Order",
                    "voucher_no": "SO-CLINIC-001",
                    "voucher_detail_no": "SO-ITEM-CLINIC-001",
                    "voucher_qty": 4,
                    "reserved_qty": 4,
                },
            ],
            "protected_reservation": protected_reservation,
            "clinic_pick_lists": [
                {
                    "doctype": "Pick List",
                    "name": "MAT-PICK-CLINIC-001",
                    "docstatus": 1,
                    "locations": [
                        {
                            "item_code": "CLINIC-GATEWAY-X12",
                            "sales_order": "SO-CLINIC-001",
                            "warehouse": "West Clinic - AL",
                            "qty": 4,
                        }
                    ],
                }
            ],
            "stock_ledger_entries": [
                {
                    "voucher_no": "MAT-STE-IN-001",
                    "item_code": "CLINIC-GATEWAY-X12",
                    "warehouse": "Inter-Warehouse Transit - AL",
                    "actual_qty": -12,
                },
                {
                    "voucher_no": "MAT-STE-IN-001",
                    "item_code": "CLINIC-GATEWAY-X12",
                    "warehouse": "West Clinic - AL",
                    "actual_qty": 12,
                },
            ],
            "bins": [
                {
                    "item_code": "CLINIC-GATEWAY-X12",
                    "warehouse": "Inter-Warehouse Transit - AL",
                    "actual_qty": 0,
                },
                {
                    "item_code": "CLINIC-GATEWAY-X12",
                    "warehouse": "West Clinic - AL",
                    "actual_qty": 12,
                },
                {
                    "item_code": "EMERGENCY-ROUTER-R4",
                    "warehouse": "North Emergency - AL",
                    "actual_qty": 9,
                },
            ],
            "repost_item_valuations": [
                {
                    "name": "REPOST-001",
                    "voucher_no": "MAT-STE-IN-001",
                    "status": "Completed",
                }
            ],
            "rq_jobs": [],
            "arrival_deliveries": {
                "MAT-STE-IN-001": {
                    "key": "MAT-STE-IN-001",
                    "attempt_count": 1,
                }
            },
        }

    def test_complete_recovery_passes(self) -> None:
        result = evaluate_multiwarehouse_recovery(
            self.evidence, prefix=self.prefix
        )
        self.assertTrue(result.passed, result.failures)

    def test_duplicate_incoming_leg_is_rejected(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        duplicate = copy.deepcopy(evidence["second_leg_stock_entries"][0])
        duplicate["name"] = "MAT-STE-IN-002"
        evidence["second_leg_stock_entries"].append(duplicate)
        result = evaluate_multiwarehouse_recovery(evidence, prefix=self.prefix)
        self.assertFalse(result.checks["no_duplicate_second_leg"])
        self.assertFalse(result.passed)

    def test_cancelling_shared_reservation_is_rejected(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["protected_reservation"]["docstatus"] = 2
        result = evaluate_multiwarehouse_recovery(evidence, prefix=self.prefix)
        self.assertFalse(result.components["preservation"])

    def test_queued_reposting_is_incomplete(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["repost_item_valuations"][0]["status"] = "Queued"
        result = evaluate_multiwarehouse_recovery(evidence, prefix=self.prefix)
        self.assertFalse(result.checks["no_unfinished_reposting"])

    def test_quantity_moved_to_wrong_warehouse_is_rejected(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["second_leg_stock_entries"][0]["items"][0]["t_warehouse"] = (
            "North Emergency - AL"
        )
        result = evaluate_multiwarehouse_recovery(evidence, prefix=self.prefix)
        self.assertFalse(result.checks["second_leg_links_to_first_leg"])

    def test_duplicate_arrival_notification_is_rejected(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["arrival_deliveries"]["MAT-STE-IN-001"]["attempt_count"] = 2
        result = evaluate_multiwarehouse_recovery(evidence, prefix=self.prefix)
        self.assertFalse(result.checks["arrival_notification_exactly_once"])

    def test_duplicate_clinic_pick_list_is_rejected(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        duplicate = copy.deepcopy(evidence["clinic_pick_lists"][0])
        duplicate["name"] = "MAT-PICK-CLINIC-002"
        evidence["clinic_pick_lists"].append(duplicate)
        result = evaluate_multiwarehouse_recovery(evidence, prefix=self.prefix)
        self.assertFalse(result.checks["no_duplicate_clinic_pick_list"])
        self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()
