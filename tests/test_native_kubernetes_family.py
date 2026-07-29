from __future__ import annotations

import json
import unittest

from aftermath_bench.native_kubernetes_family import (
    KUBERNETES_TOOL_DEFINITIONS,
    kubernetes_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root


class NativeKubernetesFamilyTests(unittest.TestCase):
    def setUp(self):
        self.scenario = load_native_scenario(
            repository_root()
            / "data"
            / "scenario_blueprints"
            / "k8s-deployment-rollout-dev-001"
            / "scenario.json"
        )

    def test_registry_selects_kubernetes_family(self):
        family = NATIVE_FAMILY_REGISTRY.get(self.scenario.raw["family"])
        self.assertEqual(family.domain, "kubernetes")
        self.assertEqual(
            family.tool_definitions, KUBERNETES_TOOL_DEFINITIONS
        )

    def test_tools_are_generic_closed_kubernetes_operations(self):
        names = {tool.name for tool in KUBERNETES_TOOL_DEFINITIONS}
        self.assertEqual(
            names,
            {
                "get_object",
                "list_objects",
                "list_events",
                "patch_object",
                "remove_node_taint",
                "wait_for_rollout",
            },
        )
        for tool in KUBERNETES_TOOL_DEFINITIONS:
            self.assertFalse(tool.input_schema["additionalProperties"])
            self.assertNotIn(
                "recommended", json.dumps(tool.input_schema).lower()
            )

    def test_initial_message_never_reveals_hidden_variant(self):
        message = kubernetes_initial_message(
            scenario=self.scenario,
            prefix={"trace": []},
            failure_report={
                "visible_failure": {
                    "ok": False,
                    "error": "HTTP connection lost before a success response",
                }
            },
        )
        self.assertIn("checkout-api", message)
        for variant in self.scenario.variants:
            self.assertNotIn(variant, message)


if __name__ == "__main__":
    unittest.main()
