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
        self.assertIn('SOURCE_RUN_ID: "30797882168"', self.text)
        self.assertIn('SOURCE_ARTIFACT_ID: "8850647675"', self.text)
        self.assertIn(
            "SOURCE_CIPHERTEXT_SHA256: "
            "8f55a91e3d0be8ae9ce26a33f8ee103528b405a21687ed114b4a1701569a81c6",
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
