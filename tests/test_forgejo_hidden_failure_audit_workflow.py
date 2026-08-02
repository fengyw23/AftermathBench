from __future__ import annotations

import unittest
from pathlib import Path


class ForgejoHiddenFailureAuditWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = Path(
            ".github/workflows/forgejo-hidden-failure-audit.yml"
        ).read_text(encoding="utf-8")

    def test_audit_is_bound_to_the_failed_encrypted_artifact(self) -> None:
        for value in (
            'SOURCE_RUN_ID: "30762877469"',
            'SOURCE_ARTIFACT_ID: "8838727089"',
            "sha256:5b9365ee76f6c6a9c0e4d1cde95301b5ee4e7eee160e38670d8f2eb8f873d4ea",
            "0d0966e66460635b849e472a0984c80d6632d5ed292b47ff1ddf61055a908462",
        ):
            self.assertIn(value, self.text)

    def test_no_provider_or_model_call_exists(self) -> None:
        self.assertNotIn("BAILIAN_API_KEY", self.text)
        self.assertNotIn("ZHIPU_CODING_API_KEY", self.text)
        self.assertNotIn("run-native-model", self.text)
        self.assertNotIn("chat/completions", self.text)

    def test_only_redacted_classification_is_uploaded(self) -> None:
        upload = self.text.index("Upload redacted classification only")
        purge = self.text.index("Purge plaintext and encrypted inputs")
        section = self.text[upload:purge]
        self.assertIn("hidden-failure-audit/public/", section)
        self.assertNotIn("hidden-failure-audit/private/", section)
        self.assertIn("classify_private_model_failures.py", self.text[:upload])


if __name__ == "__main__":
    unittest.main()
