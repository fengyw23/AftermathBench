from __future__ import annotations

import unittest
from pathlib import Path


class ERPNextHiddenConsumeWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "erpnext-hidden-consume.yml"
        ).read_text(encoding="utf-8")

    def test_provider_is_selected_before_any_hidden_artifact_is_downloaded(
        self,
    ) -> None:
        provider = self.text.index(
            "Select a working provider before hidden data access"
        )
        download = self.text.index(
            "Download and verify the preregistered sealed artifact"
        )
        decrypt = self.text.index("Decrypt and verify the exact frozen bundle")
        self.assertLess(provider, download)
        self.assertLess(download, decrypt)
        self.assertIn("BAILIAN_API_KEY", self.text)
        self.assertIn("ZHIPU_CODING_API_KEY", self.text)
        self.assertIn('"name": "provider_probe"', self.text)
        self.assertIn('get("tool_calls")', self.text)

    def test_workflow_is_bound_to_one_immutable_freeze(self) -> None:
        for token in (
            "__FREEZE_RUN_ID__",
            "__FREEZE_ARTIFACT_ID__",
            "__FREEZE_SOURCE_COMMIT__",
        ):
            self.assertNotIn(token, self.text)
        for binding in (
            'FREEZE_RUN_ID: "30804648059"',
            'FREEZE_ARTIFACT_ID: "8853263263"',
            'FREEZE_SOURCE_COMMIT: "2f5698dd0d92c5dd347052b40190e3323421a080"',
            'FREEZE_PUBLIC_COMMITMENT: "2e01eb0a0bc5c4ac06a7f35558287ea14cab4e1a3fe0da0fbd2092b6664e0b14"',
        ):
            self.assertIn(binding, self.text)
        self.assertIn("Refuse an unbound workflow template", self.text)

    def test_model_run_is_locked_and_private_results_are_reencrypted(self) -> None:
        for token in (
            "verify_frozen_bundle.py",
            "verify_hidden_test_eligibility.py",
            "--hidden-freeze",
            "--hidden-usage-ledger",
            "--hidden-evaluation-id",
            "--hidden-finalize",
            "consumed-bundle.tar.gz.enc",
            "frozen-bundle-integrity",
            "ERPNext hidden verification failed",
        ):
            self.assertIn(token, self.text)
        self.assertNotIn("include-hidden-files: true", self.text)
        self.assertIn("for attempt in 1 2", self.text)
        self.assertIn("variant-retry-restore.log", self.text)
        smoke_restore = self.text.index(
            '--snapshot "$run_root/private/bundles/boundary-$credential_probe_variant"'
        )
        credential_smoke = self.text.index("verify_erpnext_credentials.py")
        clean_restore = self.text.index(
            '--snapshot "$run_root/private/bundles/boundary-$variant"'
        )
        model = self.text.index("python -m aftermath_bench run-native-model")
        self.assertLess(smoke_restore, credential_smoke)
        self.assertLess(credential_smoke, clean_restore)
        self.assertLess(clean_restore, model)


if __name__ == "__main__":
    unittest.main()
