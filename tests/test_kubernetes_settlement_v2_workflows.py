from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


VARIANTS = (
    "orchestration_request_not_reached",
    "job_completed_downstream_absent",
    "job_suspended_partial_records",
    "delivery_committed_response_lost",
)


class KubernetesSettlementV2WorkflowTest(unittest.TestCase):
    def test_runtime_replays_references_and_fixed_policies(self) -> None:
        text = (
            repository_root()
            / ".github"
            / "workflows"
            / "kubernetes-settlement-v2-runtime.yml"
        ).read_text(encoding="utf-8")
        for variant in VARIANTS:
            self.assertIn(variant, text)
        for script in (
            "run_kubernetes_settlement_v2_boundary.py",
            "run_kubernetes_settlement_v2_control.py",
            "validate_kubernetes_settlement_v2_replay.py",
            "run_kubernetes_settlement_v2_baseline.py",
        ):
            self.assertIn(script, text)
        self.assertNotIn("BAILIAN_API_KEY", text)

    def test_model_uses_secret_and_never_embeds_it(self) -> None:
        text = (
            repository_root()
            / ".github"
            / "workflows"
            / "kubernetes-settlement-v2-model.yml"
        ).read_text(encoding="utf-8")
        for variant in VARIANTS:
            self.assertIn(variant, text)
        self.assertIn("secrets.BAILIAN_API_KEY", text)
        self.assertIn("k8s-settlement-orchestrated-dev-002", text)
        self.assertNotIn("sk-", text)


if __name__ == "__main__":
    unittest.main()
