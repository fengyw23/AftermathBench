from __future__ import annotations

import copy
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.erpnext_shared_batch_prefix import (
    ERPNextSharedBatchPrefixBuilder,
)
from aftermath_bench.schema import repository_root


class _StockEntryAdapter:
    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None

    def call_method(self, method: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.method = method
        self.arguments = arguments
        return {
            "message": {
                "doctype": "Stock Entry",
                "purpose": arguments["purpose"],
                "items": [
                    {
                        "item_code": "SENSOR-ARRAY-Z7",
                        "qty": arguments["qty"],
                        "serial_and_batch_bundle": "STALE-BUNDLE",
                    },
                    {"item_code": "CARDIAC-MONITOR-Z7", "qty": arguments["qty"]},
                ],
            }
        }

    def create_resource(self, doctype: str, document: dict[str, Any]) -> dict[str, Any]:
        self.created = copy.deepcopy(document)
        return {"data": {**document, "doctype": doctype, "name": "STE-0001"}}


class ERPNextSharedBatchPrefixTest(unittest.TestCase):
    def setUp(self) -> None:
        path = (
            repository_root()
            / "data"
            / "instance_specs"
            / "erpnext-shared-batch-recovery-dev-001.json"
        )
        self.fixture = json.loads(Path(path).read_text(encoding="utf-8"))["fixture"]

    def test_work_order_stock_entry_carries_the_native_supplier_batch(self) -> None:
        adapter = _StockEntryAdapter()
        builder = ERPNextSharedBatchPrefixBuilder(
            adapter,  # type: ignore[arg-type]
            scenario_id="erpnext-shared-batch-recovery-dev-001",
            fixture=self.fixture,
        )
        trace: list[dict[str, Any]] = []
        document = builder._make_stock_entry(
            work_order="WO-PRIMARY",
            purpose="Material Transfer for Manufacture",
            quantity=12,
            batch_id="SUP-BATCH-Z7-2408",
            trace=trace,
        )
        self.assertEqual(document["name"], "STE-0001")
        self.assertIsNotNone(adapter.created)
        shared = adapter.created["items"][0]  # type: ignore[index]
        self.assertEqual(shared["batch_no"], "SUP-BATCH-Z7-2408")
        self.assertEqual(shared["use_serial_batch_fields"], 1)
        self.assertNotIn("serial_and_batch_bundle", shared)
        self.assertNotIn("batch_no", adapter.created["items"][1])  # type: ignore[index]

    def test_fixture_matches_the_initialized_native_company(self) -> None:
        fixture = copy.deepcopy(self.fixture)
        fixture["company"] = "Invented Company"
        builder = ERPNextSharedBatchPrefixBuilder(
            object(),  # type: ignore[arg-type]
            scenario_id="erpnext-shared-batch-recovery-dev-001",
            fixture=fixture,
        )
        with self.assertRaisesRegex(ValueError, "initialized company"):
            builder.prepare_public_fixture()

    def test_landed_cost_allocation_covers_the_entire_received_batch(self) -> None:
        shared = self.fixture["shared_component"]
        primary = self.fixture["primary_work_order"]
        secondary = self.fixture["secondary_work_order"]
        cost = self.fixture["shared_landed_cost"]
        consumed = (
            primary["ordered_quantity"] * primary["component_quantity_per_unit"]
            + secondary["ordered_quantity"] * secondary["component_quantity_per_unit"]
        )
        self.assertEqual(shared["received_quantity"], consumed)
        self.assertEqual(
            cost["primary_allocation"] + cost["secondary_allocation"],
            cost["amount"],
        )
        self.assertEqual(
            cost["primary_allocation"] / cost["secondary_allocation"],
            primary["ordered_quantity"] / secondary["ordered_quantity"],
        )

    def test_native_receipt_quantity_includes_components_per_finished_unit(self) -> None:
        path = (
            repository_root()
            / "data"
            / "instance_specs"
            / "erpnext-shared-batch-recovery-public-dev-002.json"
        )
        fixture = json.loads(path.read_text(encoding="utf-8"))["fixture"]
        self.assertEqual(
            ERPNextSharedBatchPrefixBuilder._required_component_quantity(
                fixture["primary_work_order"]
            ),
            20.0,
        )
        self.assertEqual(
            ERPNextSharedBatchPrefixBuilder._required_component_quantity(
                fixture["secondary_work_order"]
            ),
            12.0,
        )

    def test_native_document_series_is_derived_from_the_instance(self) -> None:
        self.assertEqual(
            ERPNextSharedBatchPrefixBuilder._naming_series_for_first_document(
                "SO-WARD-001"
            ),
            "SO-WARD-.###",
        )
        with self.assertRaisesRegex(ValueError, "first value"):
            ERPNextSharedBatchPrefixBuilder._naming_series_for_first_document(
                "SO-WARD-002"
            )

    def test_actual_time_logs_start_after_all_native_scheduled_slots(self) -> None:
        start = ERPNextSharedBatchPrefixBuilder._execution_start_after_schedule(
            [
                {
                    "scheduled_time_logs": [
                        {"to_time": "2026-08-04 10:00:00"},
                        {"to_time": "2026-08-04 12:30:00"},
                    ]
                },
                {"scheduled_time_logs": [{"to_time": "2026-08-04 11:00:00"}]},
            ],
            fallback=datetime(2026, 8, 4, 8, tzinfo=UTC),
        )
        self.assertEqual(start, datetime(2026, 8, 4, 13, 30, tzinfo=UTC))


if __name__ == "__main__":
    unittest.main()
