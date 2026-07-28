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


if __name__ == "__main__":
    unittest.main()
