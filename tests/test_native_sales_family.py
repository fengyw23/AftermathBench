from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_sales_family import (
    SALES_RETURN_TOOL_DEFINITIONS,
    diagnose_sales_trajectory,
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

    def test_diagnosis_detects_stale_plan_after_delivery_submission(self) -> None:
        turns = [
            {
                "tool_calls": [
                    {
                        "name": "get_document",
                        "arguments": {
                            "doctype": "Delivery Note",
                            "name": "DN-REPLACEMENT",
                        },
                    },
                    {
                        "name": "find_background_jobs",
                        "arguments": {"reference": "DN-RETURN"},
                    },
                    {
                        "name": "get_external_delivery",
                        "arguments": {"reference": "DN-RETURN"},
                    },
                    {
                        "name": "submit_document",
                        "arguments": {
                            "doctype": "Delivery Note",
                            "name": "DN-REPLACEMENT",
                        },
                    },
                    {
                        "name": "create_sales_invoice_from_order",
                        "arguments": {"sales_order": "SO-REPLACEMENT"},
                    },
                ],
                "tool_results": [],
            }
        ]
        evaluation = SimpleNamespace(
            passed=False,
            components={
                "goal_completion": True,
                "repair_completeness": True,
                "preservation": True,
                "protocol_safety": False,
            },
        )
        diagnostics = diagnose_sales_trajectory(
            turns=turns,
            evaluation=evaluation,
            failure_report={
                "failure_boundary_evidence": {
                    "sales_return": {"docstatus": 0},
                    "replacement_invoices": [],
                }
            },
            prefix={
                "sales_return": "DN-RETURN",
                "replacement_sales_order": "SO-REPLACEMENT",
                "replacement_delivery_note": "DN-REPLACEMENT",
            },
        )

        self.assertEqual(
            diagnostics["primary_error"],
            "investigation_failure",
        )
        self.assertEqual(
            diagnostics["failure_subtype"],
            "post_mutation_state_not_refreshed",
        )
        self.assertTrue(
            diagnostics[
                "created_invoice_after_delivery_without_state_refresh"
            ]
        )


if __name__ == "__main__":
    unittest.main()
