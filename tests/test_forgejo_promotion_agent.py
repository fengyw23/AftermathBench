from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from aftermath_bench.integrations.forgejo_promotion_agent import (
    ForgejoPromotionEnvironment,
)
from aftermath_bench.integrations.forgejo_promotion_baselines import (
    FORGEJO_PROMOTION_BASELINES,
    run_fixed_forgejo_promotion_baseline,
)


class ForgejoPromotionAgentTest(unittest.TestCase):
    def test_public_surface_has_cross_system_reads_without_repair_tool(self) -> None:
        names = set(ForgejoPromotionEnvironment.TOOL_NAMES)
        self.assertTrue(
            {
                "list_action_runs",
                "list_action_run_artifacts",
                "get_deployment_state",
                "get_external_attestation",
                "dispatch_workflow",
            }.issubset(names)
        )
        self.assertFalse(any(name.startswith("repair_") for name in names))

    def test_fixed_baselines_are_state_insensitive_and_distinct(self) -> None:
        traces = {}
        for baseline in FORGEJO_PROMOTION_BASELINES:
            environment = Mock()
            environment.instance = SimpleNamespace(
                workflow_path=".forgejo/workflows/promote.yml",
                version="6.2.0",
                artifact_digest="sha256:approved",
                attestation_key="attestation:key",
                release_tag="v6.2.0",
            )
            environment.prefix = {"rollout_issue_index": 2}

            def invoke(tool: str, **arguments):
                if tool == "list_action_runs":
                    return {"ok": True, "result": [{"id": 7}]}
                if tool == "dispatch_workflow":
                    return {"ok": True, "result": {"id": 8}}
                return {"ok": True, "result": {}}

            environment.invoke.side_effect = invoke
            traces[baseline] = run_fixed_forgejo_promotion_baseline(
                baseline, environment=environment
            )

        self.assertEqual(traces["no_op"], ())
        self.assertNotEqual(
            traces["resume_after_bundle"], traces["resume_after_deployment"]
        )
        self.assertTrue(
            any(
                event["tool"] == "start_action_runner"
                for event in traces["start_runner_then_finalize"]
            )
        )


if __name__ == "__main__":
    unittest.main()
