from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "erpnext-hidden-failure-audit.yml"


class ERPNextHiddenFailureAuditWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_is_bound_to_the_failed_encrypted_artifact(self) -> None:
        self.assertIn('SOURCE_RUN_ID: "30786512162"', self.text)
        self.assertIn('SOURCE_ARTIFACT_ID: "8845660300"', self.text)
        self.assertIn(
            "SOURCE_CIPHERTEXT_SHA256: "
            "fd1600226eef1481383241bc3a6b6bd8e722079b36daaf16c9b2de4c87d03966",
            self.text,
        )
        self.assertIn('"four_run_errors"', self.text)

    def test_only_redacted_classification_is_published(self) -> None:
        upload = self.text.index("Upload redacted classification only")
        purge = self.text.index("Purge plaintext and encrypted inputs")
        section = self.text[upload:purge]
        self.assertIn("hidden-failure-audit/public/", section)
        self.assertNotIn("hidden-failure-unsealed", section)
        self.assertNotIn("consumed-bundle.tar.gz.enc", section)
        self.assertIn("classify_private_model_failures.py", self.text)

    def test_audit_does_not_call_a_model_or_modify_usage_ledger(self) -> None:
        self.assertNotIn("run-native-model", self.text)
        self.assertNotIn("hidden-finalize", self.text)
        self.assertNotIn("usage-ledger.json", self.text)


if __name__ == "__main__":
    unittest.main()
