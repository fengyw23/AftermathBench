from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from aftermath_bench.integrations.erpnext_inventory_cost_agent import (
    ERPNextInventoryCostEnvironment,
)
from aftermath_bench.schema import repository_root


class ERPNextInventoryCostAgentTest(unittest.TestCase):
    def test_public_surface_has_generic_reads_and_state_advancing_tools(self) -> None:
        self.assertIn("get_document", ERPNextInventoryCostEnvironment.TOOL_NAMES)
        self.assertIn("list_documents", ERPNextInventoryCostEnvironment.TOOL_NAMES)
        self.assertIn(
            "run_stock_reposting_scheduler",
            ERPNextInventoryCostEnvironment.TOOL_NAMES,
        )
        self.assertNotIn("inspect_inventory_cost_state", ERPNextInventoryCostEnvironment.TOOL_NAMES)
        self.assertNotIn("repair_inventory_cost", ERPNextInventoryCostEnvironment.TOOL_NAMES)
        self.assertEqual(len(ERPNextInventoryCostEnvironment.MUTATION_TOOLS), 6)
        self.assertIn(
            "wait_for_external_delivery",
            ERPNextInventoryCostEnvironment.MUTATION_TOOLS,
        )

    def test_scheduler_tool_executes_pinned_native_reposting_function(self) -> None:
        environment = object.__new__(ERPNextInventoryCostEnvironment)
        environment.stack = MagicMock()
        environment.stack.process_repost_item_valuation_queue.return_value = {
            "processed": True,
            "source_function": (
                "erpnext.stock.doctype.repost_item_valuation."
                "repost_item_valuation.repost_entries"
            ),
        }
        result = environment._run_reposting_scheduler()
        self.assertTrue(result["ok"])
        self.assertTrue(result["processed"])
        environment.stack.process_repost_item_valuation_queue.assert_called_once_with()

    def test_reference_queries_item_based_landed_cost_repost_owners(self) -> None:
        source = (
            repository_root()
            / "src"
            / "aftermath_bench"
            / "integrations"
            / "erpnext_inventory_cost_agent.py"
        ).read_text(encoding="utf-8")
        self.assertIn('filters={"via_landed_cost_voucher": 1}', source)


if __name__ == "__main__":
    unittest.main()
