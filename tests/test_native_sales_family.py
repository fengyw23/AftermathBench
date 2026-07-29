from __future__ import annotations

import json
import unittest

from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_sales_family import (
    SALES_RETURN_TOOL_DEFINITIONS,
    sales_initial_message,
)
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root


class NativeSalesFamilyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = load_native_scenario(
            repository_root()
            / "data"
            / "scenario_blueprints"
            / "erpnext-sales-return-dev-001"
            / "scenario.json"
        )

    def test_registry_selects_sales_family(self) -> None:
        family = NATIVE_FAMILY_REGISTRY.get(self.scenario.raw["family"])
        self.assertEqual(family.domain, "erpnext")
        self.assertEqual(family.tool_definitions, SALES_RETURN_TOOL_DEFINITIONS)

    def test_tools_are_closed_and_do_not_recommend_recovery(self) -> None:
        names = {tool.name for tool in SALES_RETURN_TOOL_DEFINITIONS}
        self.assertIn("list_related_documents", names)
        self.assertIn("create_sales_return", names)
        self.assertIn("create_sales_invoice_from_order", names)
        self.assertNotIn("create_sales_invoice_from_delivery", names)
        self.assertNotIn("repair_sales_return", names)
        for tool in SALES_RETURN_TOOL_DEFINITIONS:
            self.assertFalse(tool.input_schema["additionalProperties"])
            self.assertNotIn(
                "recommended",
                json.dumps(tool.input_schema).lower(),
            )

    def test_initial_message_does_not_reveal_variant(self) -> None:
        message = sales_initial_message(
            scenario=self.scenario,
            prefix={
                "sales_return": "DN-RETURN",
                "trace": [],
            },
            failure_report={
                "visible_failure": {
                    "ok": False,
                    "error": "connection_lost_before_confirmation",
                }
            },
        )
        self.assertIn("DN-RETURN", message)
        for variant in self.scenario.variants:
            self.assertNotIn(variant, message)


if __name__ == "__main__":
    unittest.main()
