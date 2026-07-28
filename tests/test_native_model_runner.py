import json
import unittest
from pathlib import Path

from aftermath_bench.native_model_runner import (
    NATIVE_RETURN_TOOL_DEFINITIONS,
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


if __name__ == "__main__":
    unittest.main()
