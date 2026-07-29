from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ForgejoModelWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (
            ROOT / ".github" / "workflows" / "forgejo-model.yml"
        ).read_text(encoding="utf-8")

    def test_builds_source_and_runs_all_native_variants(self):
        self.assertIn("scripts/build_forgejo_runtime.py", self.workflow)
        self.assertIn("--build", self.workflow)
        for variant in (
            "merge_request_not_reached",
            "merge_committed_delivery_succeeded",
            "merge_committed_receiver_accepted_response_lost",
            "merge_committed_delivery_request_not_reached",
        ):
            self.assertIn(variant, self.workflow)
        self.assertIn("run-native-model", self.workflow)
        self.assertIn("summarize_native_model_runs.py", self.workflow)

    def test_uses_secret_and_removes_runtime_credentials(self):
        self.assertIn("secrets.BAILIAN_API_KEY", self.workflow)
        self.assertIn("rm -f \"$runtime_root/credentials.json\"", self.workflow)
        upload = self.workflow.split("uses: actions/upload-artifact@v4", 1)[1]
        self.assertNotIn("credentials.json", upload)
        self.assertNotIn("release-prefix.tar.gz", upload)


if __name__ == "__main__":
    unittest.main()
