from __future__ import annotations

import unittest
from pathlib import Path


class ERPNextHiddenFreezeMetadataWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "erpnext-hidden-freeze-metadata.yml"
        ).read_text(encoding="utf-8")

    def test_is_bound_to_the_successful_provider_free_freeze(self) -> None:
        self.assertIn('SOURCE_RUN_ID: "30794490591"', self.text)
        self.assertIn('SOURCE_ARTIFACT_ID: "8849278840"', self.text)
        self.assertIn("f288db129424ffba9db39b576da91e3092de8b53", self.text)
        self.assertIn("frozen_unseen", self.text)
        self.assertIn('result["usage_state"] == "frozen"', self.text)

    def test_publishes_only_preexisting_safe_metadata(self) -> None:
        self.assertNotIn("HIDDEN_BUNDLE_ENCRYPTION_KEY", self.text)
        self.assertNotIn("openssl enc -d", self.text)
        self.assertNotIn("run-native-model", self.text)
        self.assertNotIn("AFTERMATH_API_KEY", self.text)
        self.assertIn("publish-safe-freeze-verdict", self.text)
        self.assertIn("public_commitment", self.text)
        self.assertIn("ciphertext_sha256", self.text)


if __name__ == "__main__":
    unittest.main()
