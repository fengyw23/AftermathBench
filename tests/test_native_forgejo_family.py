from __future__ import annotations

import json
import unittest

from aftermath_bench.native_forgejo_family import (
    FORGEJO_TOOL_DEFINITIONS,
    forgejo_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root


class NativeForgejoFamilyTests(unittest.TestCase):
    def setUp(self):
        self.scenario = load_native_scenario(
            repository_root()
            / "data"
            / "scenario_blueprints"
            / "forgejo-pr-release-dev-001"
            / "scenario.json"
        )

    def test_registry_selects_forgejo_family(self):
        family = NATIVE_FAMILY_REGISTRY.get(self.scenario.raw["family"])
        self.assertEqual(family.domain, "forgejo")
        self.assertEqual(family.tool_definitions, FORGEJO_TOOL_DEFINITIONS)

    def test_tools_are_closed_and_not_answer_style(self):
        names = {tool.name for tool in FORGEJO_TOOL_DEFINITIONS}
        self.assertIn("get_webhook_history", names)
        self.assertIn("list_external_deliveries", names)
        self.assertIn("replay_webhook", names)
        self.assertNotIn("repair_release", names)
        for tool in FORGEJO_TOOL_DEFINITIONS:
            self.assertFalse(tool.input_schema["additionalProperties"])
            self.assertNotIn(
                "recommended", json.dumps(tool.input_schema).lower()
            )

    def test_initial_message_never_reveals_hidden_variant(self):
        prefix = {
            **self.scenario.raw["fixture"],
            "webhook_id": 1,
            "trace": [],
        }
        message = forgejo_initial_message(
            scenario=self.scenario,
            prefix=prefix,
            failure_report={
                "visible_failure": {
                    "ok": False,
                    "error": "HTTP connection lost before a success response",
                }
            },
        )
        self.assertIn("Pull Request #2", message)
        for variant in self.scenario.variants:
            self.assertNotIn(variant, message)


if __name__ == "__main__":
    unittest.main()
