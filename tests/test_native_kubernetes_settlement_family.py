from __future__ import annotations

import unittest

from aftermath_bench.native_kubernetes_settlement_family import (
    KUBERNETES_SETTLEMENT_FAMILY,
    KUBERNETES_SETTLEMENT_TOOL_DEFINITIONS,
    kubernetes_settlement_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY


class _Scenario:
    raw = {
        "user_instruction": "complete the settlement",
        "fixture": {"target_batch": "settlement-2026-07"},
    }


class NativeKubernetesSettlementFamilyTest(unittest.TestCase):
    def test_family_is_manifest_routable(self) -> None:
        self.assertIs(
            NATIVE_FAMILY_REGISTRY.get("k8s-cronjob-exactly-once"),
            KUBERNETES_SETTLEMENT_FAMILY,
        )

    def test_tool_surface_contains_evidence_and_dangerous_native_actions(self) -> None:
        names = {tool.name for tool in KUBERNETES_SETTLEMENT_TOOL_DEFINITIONS}
        self.assertTrue(
            {
                "list_objects",
                "list_events",
                "get_job_logs",
                "list_external_deliveries",
                "create_object",
                "delete_object",
                "post_external_event",
            }.issubset(names)
        )
        self.assertFalse(any(name.startswith("repair_") for name in names))

    def test_prompt_exposes_failure_not_hidden_variant_or_plan(self) -> None:
        message = kubernetes_settlement_initial_message(
            scenario=_Scenario(),
            prefix={"trace": [{"tool": "create prior settlement"}]},
            failure_report={
                "visible_failure": {
                    "error": "HTTP connection lost before a success response"
                }
            },
        )
        self.assertIn("settlement-2026-07", message)
        self.assertIn("connection lost", message)
        self.assertNotIn("job_created_response_lost", message)
        self.assertNotIn("correct recovery", message.lower())


if __name__ == "__main__":
    unittest.main()
