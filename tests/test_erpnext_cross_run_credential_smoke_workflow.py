from __future__ import annotations

import unittest
from pathlib import Path


class ERPNextCrossRunCredentialSmokeWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "erpnext-cross-run-credential-smoke.yml"
        ).read_text(encoding="utf-8")

    def test_destroys_the_source_runtime_before_restore(self) -> None:
        snapshot = self.text.index("snapshot-bundle")
        purge = self.text.index("manage_erpnext_stack.py purge", snapshot)
        second_up = self.text.index("manage_erpnext_stack.py up", purge)
        restore = self.text.index("restore-bundle", second_up)
        credential = self.text.index("verify_erpnext_credentials.py", restore)
        self.assertLess(snapshot, purge)
        self.assertLess(purge, second_up)
        self.assertLess(second_up, restore)
        self.assertLess(restore, credential)

    def test_smoke_is_provider_free_and_checks_minimal_schema(self) -> None:
        self.assertNotIn("AFTERMATH_API_KEY", self.text)
        self.assertNotIn("BAILIAN_API_KEY", self.text)
        self.assertNotIn("ZHIPU_CODING_API_KEY", self.text)
        self.assertNotIn("run-native-model", self.text)
        self.assertIn('manifest["schema_version"] == "1.2"', self.text)
        self.assertIn('set(crypto) == {"encryption_key"}', self.text)


if __name__ == "__main__":
    unittest.main()
