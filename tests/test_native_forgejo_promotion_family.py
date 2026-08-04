from __future__ import annotations

import unittest

from aftermath_bench.native_forgejo_promotion_family import (
    FORGEJO_PROMOTION_FAMILY,
    FORGEJO_PROMOTION_TOOLS,
    forgejo_promotion_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root


class NativeForgejoPromotionFamilyTest(unittest.TestCase):
    def setUp(self) -> None:
        root = repository_root()
        self.scenario = load_native_scenario(
            root
            / "data"
            / "scenario_blueprints"
            / "forgejo-approved-artifact-promotion-public-dev-001"
            / "scenario.json"
        )
        self.prefix = {
            "owner": "aftermath",
            "repository": "clinical-alert-router",
            "rollout_issue_index": 2,
            "approval_issue_index": 1,
            "unrelated_issue_index": 3,
            "workflow_path": ".forgejo/workflows/promote-production.yml",
            "release_tag": "v6.2.0",
            "protected_release_tag": "v6.1.4",
            "repository_head": "approved-head",
            "trace": [
                {
                    "system": "forgejo",
                    "tool": "create_release",
                    "arguments": {"tag": "v6.1.4"},
                    "result": {"secret_internal_detail": "not model input"},
                    "status": "success",
                }
            ],
        }

    def test_family_is_registered_with_cross_system_tools(self) -> None:
        self.assertIs(
            NATIVE_FAMILY_REGISTRY.get("forgejo-approved-artifact-promotion"),
            FORGEJO_PROMOTION_FAMILY,
        )
        names = {tool.name for tool in FORGEJO_PROMOTION_TOOLS}
        self.assertTrue(
            {
                "get_repository_content",
                "list_action_runs",
                "list_action_run_artifacts",
                "get_deployment_state",
                "get_external_attestation",
                "dispatch_workflow",
            }.issubset(names)
        )

    def test_initial_message_hides_variant_and_prefix_results(self) -> None:
        message = forgejo_promotion_initial_message(
            scenario=self.scenario,
            prefix=self.prefix,
            failure_report={
                "variant": "dispatch_request_not_reached",
                "latest_attempt": {
                    "tool": "dispatch_workflow",
                    "result": {"error": "connection lost"},
                },
            },
        )
        self.assertNotIn("dispatch_request_not_reached", message)
        self.assertNotIn("secret_internal_detail", message)
        self.assertIn("connection lost", message)
        self.assertIn("create_release", message)


if __name__ == "__main__":
    unittest.main()
