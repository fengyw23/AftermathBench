from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class KubernetesSettlementWorkflowTest(unittest.TestCase):
    def test_workflow_replays_every_native_variant(self) -> None:
        text = (
            repository_root()
            / ".github"
            / "workflows"
            / "kubernetes-settlement-runtime.yml"
        ).read_text(encoding="utf-8")
        for variant in (
            "job_create_request_not_reached",
            "job_created_response_lost",
            "job_created_controller_suspended",
            "job_created_pod_pending",
        ):
            self.assertIn(variant, text)
        self.assertIn("run_kubernetes_settlement_control.py", text)
        self.assertIn("validate_kubernetes_settlement_replay.py", text)
        self.assertIn("run_kubernetes_settlement_baseline.py", text)
        self.assertIn("summarize_native_baselines.py", text)
        self.assertIn("kubernetes-control:local", text)
        self.assertIn("webhook_sink", text)

    def test_workflow_does_not_embed_provider_credentials(self) -> None:
        text = (
            repository_root()
            / ".github"
            / "workflows"
            / "kubernetes-settlement-runtime.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("sk-", text)
        self.assertNotIn("BAILIAN_API_KEY", text)


if __name__ == "__main__":
    unittest.main()
