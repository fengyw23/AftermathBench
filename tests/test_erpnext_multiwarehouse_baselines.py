from __future__ import annotations

import unittest
from typing import ClassVar

from aftermath_bench.integrations.erpnext_multiwarehouse_baselines import (
    BASELINE_NAMES,
    run_multiwarehouse_baseline,
)


class _FakeEnvironment:
    prefix: ClassVar[dict[str, object]] = {
        "second_leg_stock_entry": "STE-IN",
        "outgoing_stock_entry": "STE-OUT",
        "destination_warehouse": "Destination - AL",
        "clinic_sales_order": "SO-CLINIC",
        "transfer_item": "ITEM-A",
        "clinic_reserved_quantity": 4,
        "protected_reservation": "SRE-PROTECTED",
    }

    def invoke(self, tool: str, **arguments: object) -> dict[str, object]:
        if tool == "get_document":
            return {"ok": True, "document": {"name": "STE-IN", "docstatus": 0}}
        if tool in {
            "create_stock_reservation_entry",
            "create_second_transfer_leg",
        }:
            return {"ok": True, "document": {"name": f"NEW-{tool}"}}
        return {"ok": True, "tool": tool, "arguments": arguments}


class ERPNextMultiwarehouseBaselineTests(unittest.TestCase):
    def test_all_declared_baselines_execute_through_public_tools(self) -> None:
        environment = _FakeEnvironment()
        for name in BASELINE_NAMES:
            with self.subTest(name=name):
                trace = run_multiwarehouse_baseline(name, environment)  # type: ignore[arg-type]
                self.assertIsInstance(trace, tuple)

    def test_unknown_baseline_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_multiwarehouse_baseline("unknown", _FakeEnvironment())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
