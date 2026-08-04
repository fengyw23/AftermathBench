from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aftermath_bench.integrations.erpnext_inventory_cost_baselines import (
    INVENTORY_COST_BASELINE_NAMES,
    run_fixed_inventory_cost_baseline,
)
from scripts.summarize_erpnext_inventory_cost_baselines import summarize


class _Environment:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def invoke(self, tool: str, **arguments: object) -> dict[str, object]:
        self.calls.append((tool, arguments))
        return {"ok": True}


class InventoryCostBaselinesTest(unittest.TestCase):
    def test_fixed_policies_are_distinct_and_nonadaptive(self) -> None:
        self.assertEqual(len(INVENTORY_COST_BASELINE_NAMES), 7)
        environment = _Environment()
        trace = run_fixed_inventory_cost_baseline(
            "blind_submit",
            environment=environment,  # type: ignore[arg-type]
            prefix={"landed_cost_voucher": "LCV-1"},
        )
        self.assertEqual(trace[0]["tool"], "submit_document")

    def test_summary_rejects_missing_native_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            scenario = Path(directory) / "scenario.json"
            scenario.write_text(
                '{"schema_version":"0.1","scenario_id":"x",'
                '"family_id":"erpnext-inventory-cost-settlement",'
                '"domain":"erpnext","user_instruction":"x",'
                '"matched_variants":[{"id":"a"},{"id":"b"}]}'
            )
            result = summarize(Path(directory), scenario)
        self.assertFalse(result["passed"])
        self.assertTrue(result["missing_reports"])


if __name__ == "__main__":
    unittest.main()
