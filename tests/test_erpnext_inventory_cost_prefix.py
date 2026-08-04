from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.erpnext_inventory_cost_prefix import (
    ERPNextInventoryCostPrefixBuilder,
)
from aftermath_bench.schema import repository_root


class _StockEntryAdapter:
    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None

    def call_method(self, method: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "message": {
                "doctype": "Stock Entry",
                "purpose": arguments["purpose"],
                "items": [
                    {
                        "item_code": "SENSOR-MODULE-R8",
                        "qty": arguments["qty"],
                        "serial_and_batch_bundle": "STALE-BUNDLE",
                    },
                    {"item_code": "CARDIAC-MONITOR-R8", "qty": arguments["qty"]},
                ],
            }
        }

    def create_resource(self, doctype: str, document: dict[str, Any]) -> dict[str, Any]:
        self.created = copy.deepcopy(document)
        return {"data": {**document, "doctype": doctype, "name": "STE-0001"}}

    def submit_document(self, doctype: str, name: str) -> dict[str, Any]:
        assert self.created is not None
        return {"message": {**self.created, "doctype": doctype, "name": name, "docstatus": 1}}


class ERPNextInventoryCostPrefixTest(unittest.TestCase):
    def setUp(self) -> None:
        path = (
            repository_root()
            / "data"
            / "instance_specs"
            / "erpnext-inventory-cost-settlement-public-dev-001.json"
        )
        self.fixture = json.loads(Path(path).read_text(encoding="utf-8"))["fixture"]

    def test_production_entry_carries_the_native_supplier_batch(self) -> None:
        adapter = _StockEntryAdapter()
        builder = ERPNextInventoryCostPrefixBuilder(
            adapter,  # type: ignore[arg-type]
            scenario_id="erpnext-inventory-cost-settlement-public-dev-001",
            fixture=self.fixture,
        )
        trace: list[dict[str, Any]] = []
        document = builder._make_stock_entry(
            "WO-PRIMARY",
            purpose="Material Transfer for Manufacture",
            quantity=12,
            batch_id="SUP-BATCH-R8-2608",
            trace=trace,
        )
        self.assertEqual(document["docstatus"], 1)
        self.assertIsNotNone(adapter.created)
        shared = adapter.created["items"][0]  # type: ignore[index]
        self.assertEqual(shared["batch_no"], "SUP-BATCH-R8-2608")
        self.assertEqual(shared["use_serial_batch_fields"], 1)
        self.assertNotIn("serial_and_batch_bundle", shared)

    def test_fixture_uses_an_isolated_first_sales_order_series(self) -> None:
        self.assertEqual(
            self.fixture["customer_reservation"]["sales_order"], "SO-WARD-001"
        )

    def test_source_receipt_precedes_the_draft_landed_cost_boundary(self) -> None:
        source = (
            repository_root()
            / "src"
            / "aftermath_bench"
            / "integrations"
            / "erpnext_inventory_cost_prefix.py"
        ).read_text(encoding="utf-8")
        receipt = source.index('"submit shared Purchase Receipt"')
        manufacture = source.index("primary_manufacture = self._make_stock_entry")
        landed = source.index('"create draft Landed Cost Voucher"')
        self.assertLess(receipt, manufacture)
        self.assertLess(manufacture, landed)


if __name__ == "__main__":
    unittest.main()
