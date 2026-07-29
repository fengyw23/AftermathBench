from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class KubernetesSettlementModelWorkflowTest(unittest.TestCase):
    def test_workflow_uses_bailian_secret_and_all_variants(self) -> None:
        text = (
            repository_root()
            / ".github"
            / "workflows"
            / "kubernetes-settlement-model.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("secrets.BAILIAN_API_KEY", text)
        self.assertIn("run-native-model", text)
        self.assertIn("summarize_native_model_runs.py", text)
        for variant in (
            "job_create_request_not_reached",
            "job_created_response_lost",
            "job_created_controller_suspended",
            "job_created_pod_pending",
        ):
            self.assertIn(variant, text)

    def test_workflow_sanitizes_runtime_credentials(self) -> None:
        text = (
            repository_root()
            / ".github"
            / "workflows"
            / "kubernetes-settlement-model.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('rm -f "$run_root/credentials.json"', text)
        self.assertNotIn("sk-", text)


if __name__ == "__main__":
    unittest.main()
