import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from aftermath_bench.native_model_runner import (
    NATIVE_RETURN_TOOL_DEFINITIONS,
    _diagnose,
    native_initial_message,
)
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root


class NativeModelRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = load_native_scenario(
            repository_root()
            / "data"
            / "scenarios"
            / "erpnext-partial-return-dev-001"
            / "scenario.json"
        )

    def test_input_never_reveals_hidden_variant(self) -> None:
        prefix = {
            "company": "Aftermath Laboratories LLC",
            "supplier": "Northwind Scientific",
            "purchase_return": "PR-RET-1",
            "trace": [{"kind": "write", "tool": "create return"}],
        }
        message = native_initial_message(
            scenario=self.scenario,
            prefix=prefix,
            failure_report={
                "visible_failure": {
                    "ok": False,
                    "error": "connection_lost_before_confirmation",
                }
            },
        )
        self.assertIn("PR-RET-1", message)
        for variant in self.scenario.variants:
            self.assertNotIn(variant, message)

    def test_tools_are_generic_and_schemas_are_closed(self) -> None:
        names = {tool.name for tool in NATIVE_RETURN_TOOL_DEFINITIONS}
        self.assertIn("get_document", names)
        self.assertIn("submit_document", names)
        self.assertNotIn("repair_purchase_return", names)
        self.assertNotIn("get_recommended_action", names)
        list_documents = next(
            tool
            for tool in NATIVE_RETURN_TOOL_DEFINITIONS
            if tool.name == "list_documents"
        )
        self.assertIn(
            "Webhook",
            list_documents.input_schema["properties"]["doctype"]["enum"],
        )
        for tool in NATIVE_RETURN_TOOL_DEFINITIONS:
            self.assertFalse(tool.input_schema["additionalProperties"])
            self.assertNotIn("hidden", json.dumps(tool.input_schema).lower())

    def test_execution_control_supplies_scope_but_not_hidden_state(self) -> None:
        message = native_initial_message(
            scenario=self.scenario,
            prefix={
                "purchase_return": "PR-RET-1",
                "trace": [],
            },
            failure_report={
                "visible_failure": {
                    "ok": False,
                    "error": "connection_lost_before_confirmation",
                }
            },
            execution_control=True,
        )
        self.assertIn("correct recovery scope is supplied", message)
        self.assertIn("shared Payment Entry", message)
        self.assertIn("Search the Purchase Invoices", message)
        self.assertIn("never create a second", message)
        for variant in self.scenario.variants:
            self.assertNotIn(variant, message)

    def test_success_is_not_given_a_failure_attribution(self) -> None:
        diagnostics = _diagnose(
            turns=[],
            evaluation=SimpleNamespace(
                passed=True,
                components={
                    "goal_completion": True,
                    "repair_completeness": True,
                    "preservation": True,
                    "protocol_safety": True,
                },
            ),
            failure_report={
                "failure_boundary_evidence": {
                    "purchase_return": {"docstatus": 0}
                }
            },
            prefix={"purchase_return": "PR-RET-1"},
        )
        self.assertIsNone(diagnostics["primary_error"])

    @staticmethod
    def _failed_protocol_evaluation():
        return SimpleNamespace(
            passed=False,
            checks={"no_duplicate_replacement_invoice": False},
            components={
                "goal_completion": True,
                "repair_completeness": True,
                "preservation": True,
                "protocol_safety": False,
            },
        )

    def test_missing_linked_invoice_query_is_investigation_failure(
        self,
    ) -> None:
        diagnostics = _diagnose(
            turns=[
                {
                    "tool_calls": [
                        {
                            "name": "create_purchase_invoice_from_receipt",
                            "arguments": {
                                "purchase_receipt": "PR-REPLACEMENT"
                            },
                        }
                    ],
                    "tool_results": [],
                }
            ],
            evaluation=self._failed_protocol_evaluation(),
            failure_report={
                "failure_boundary_evidence": {
                    "purchase_return": {"docstatus": 1},
                    "replacement_invoices": [
                        {"name": "PINV-EXISTING", "docstatus": 0}
                    ],
                }
            },
            prefix={
                "purchase_return": "PR-RETURN",
                "replacement_purchase_receipt": "PR-REPLACEMENT",
            },
        )
        self.assertEqual(
            diagnostics["primary_error"],
            "investigation_failure",
        )
        self.assertTrue(
            diagnostics[
                "created_invoice_without_linked_invoice_investigation"
            ]
        )

    def test_duplicate_after_query_is_scope_failure(self) -> None:
        diagnostics = _diagnose(
            turns=[
                {
                    "tool_calls": [
                        {
                            "name": "list_documents",
                            "arguments": {
                                "doctype": "Purchase Invoice",
                                "filters": None,
                            },
                        },
                        {
                            "name": "get_external_delivery",
                            "arguments": {"reference": "PR-RETURN"},
                        },
                        {
                            "name": "find_background_jobs",
                            "arguments": {"reference": "PR-RETURN"},
                        },
                        {
                            "name": "create_purchase_invoice_from_receipt",
                            "arguments": {
                                "purchase_receipt": "PR-REPLACEMENT"
                            },
                        },
                    ],
                    "tool_results": [],
                }
            ],
            evaluation=self._failed_protocol_evaluation(),
            failure_report={
                "failure_boundary_evidence": {
                    "purchase_return": {"docstatus": 1},
                    "replacement_invoices": [
                        {"name": "PINV-EXISTING", "docstatus": 0}
                    ],
                }
            },
            prefix={
                "purchase_return": "PR-RETURN",
                "replacement_purchase_receipt": "PR-REPLACEMENT",
            },
        )
        self.assertEqual(diagnostics["primary_error"], "scope_failure")


if __name__ == "__main__":
    unittest.main()
