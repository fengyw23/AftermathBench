from __future__ import annotations

import unittest
from pathlib import Path


class ERPNextHiddenCandidateWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "erpnext-hidden-candidate.yml"
        ).read_text(encoding="utf-8")

    def test_freeze_precedes_any_possible_provider_access(self) -> None:
        self.assertIn("Admit and freeze before any provider request", self.text)
        self.assertNotIn("AFTERMATH_API_KEY", self.text)
        self.assertNotIn("run-native-model", self.text)
        self.assertNotIn("BAILIAN_API_KEY", self.text)
        self.assertNotIn("ZHIPU_CODING_API_KEY", self.text)

    def test_private_data_is_secret_backed_and_only_ciphertext_is_uploaded(self) -> None:
        self.assertIn("ERPNEXT_MANUFACTURING_HIDDEN_INSTANCE_B64", self.text)
        self.assertIn("ERPNEXT_MULTIWAREHOUSE_HIDDEN_INSTANCE_B64", self.text)
        self.assertIn("HIDDEN_BUNDLE_ENCRYPTION_KEY", self.text)
        self.assertIn("hidden-bundle.tar.gz.enc", self.text)
        self.assertIn("${{ runner.temp }}/erpnext-hidden/public/", self.text)
        self.assertNotIn("include-hidden-files: true", self.text)

    def test_both_families_use_native_replay_and_strict_admission(self) -> None:
        for name in ("manufacturing", "multiwarehouse"):
            self.assertIn(name, self.text)
        for token in (
            "snapshot-bundle",
            "restore-bundle",
            "reference",
            "baseline",
            "validate-native-scenario",
            "verify_hidden_test_eligibility.py",
        ):
            self.assertIn(token, self.text)


if __name__ == "__main__":
    unittest.main()
