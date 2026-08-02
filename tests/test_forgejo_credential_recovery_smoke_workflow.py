from __future__ import annotations

import unittest
from pathlib import Path


class ForgejoCredentialRecoverySmokeWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = Path(
            ".github/workflows/forgejo-credential-recovery-smoke.yml"
        ).read_text(encoding="utf-8")

    def test_uses_exact_evaluation_source_and_native_bundle_restore(self) -> None:
        self.assertIn(
            "af0b76c6a5d34cbe5a0882dfd00ff37f75fbf9c3",
            self.text,
        )
        self.assertIn("snapshot-bundle", self.text)
        self.assertIn("restore-bundle", self.text)

    def test_checks_credentials_before_and_after_restore(self) -> None:
        self.assertEqual(
            self.text.count("smoke_forgejo_credentials.py"),
            2,
        )
        restore = self.text.index("Restore state, recover credentials")
        recovery = self.text.index(
            "recover_forgejo_evaluation_credentials.py",
            restore,
        )
        smoke = self.text.index("smoke_forgejo_credentials.py", recovery)
        self.assertLess(recovery, smoke)

    def test_has_no_model_or_hidden_data_access(self) -> None:
        self.assertNotIn("run-native-model", self.text)
        self.assertNotIn("AFTERMATH_API_KEY", self.text)
        self.assertNotIn("HIDDEN_BUNDLE_ENCRYPTION_KEY", self.text)


if __name__ == "__main__":
    unittest.main()
