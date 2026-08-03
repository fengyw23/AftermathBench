from __future__ import annotations

import unittest

from aftermath_bench.integrations.erpnext_multiwarehouse_prefix import (
    MultiwarehousePrefix,
)


class ERPNextMultiwarehousePrefixTests(unittest.TestCase):
    def test_prefix_serialises_auditable_native_identifiers(self) -> None:
        prefix = MultiwarehousePrefix(
            scenario_id="erpnext-multiwarehouse-transfer-dev-001",
            company="Aftermath Laboratories LLC",
            transfer_item="CLINIC-GATEWAY-X12",
            transfer_quantity=12,
            batch_id="GW-X12-2026-08-A",
            protected_item="EMERGENCY-ROUTER-R4",
            protected_stock_balance=9,
            source_warehouse="East Distribution - AL",
            transit_warehouse="Inter-Warehouse Transit - AL",
            destination_warehouse="West Clinic - AL",
            protected_warehouse="North Emergency - AL",
            stock_seed="MAT-STE-SEED",
            material_request="MAT-MR-001",
            outgoing_stock_entry="MAT-STE-OUT",
            second_leg_stock_entry="MAT-STE-IN",
            clinic_sales_order="SAL-SO-CLINIC",
            clinic_sales_order_item="SO-ITEM-CLINIC",
            clinic_reserved_quantity=4,
            protected_sales_order="SAL-SO-NORTH",
            protected_pick_list="MAT-PICK-NORTH",
            protected_reservation="SRE-NORTH",
            arrival_webhook="Aftermath Inter-Warehouse Arrival",
            protected_fingerprints={"outgoing_stock_entry": "{}"},
            trace=(
                {
                    "kind": "write",
                    "status": "success",
                    "tool": "submit first-leg Stock Entry",
                },
            ),
        ).as_dict()
        self.assertEqual(prefix["transfer_quantity"], 12)
        self.assertEqual(prefix["second_leg_stock_entry"], "MAT-STE-IN")
        self.assertEqual(prefix["clinic_reserved_quantity"], 4)
        self.assertEqual(prefix["trace"][0]["status"], "success")


if __name__ == "__main__":
    unittest.main()
