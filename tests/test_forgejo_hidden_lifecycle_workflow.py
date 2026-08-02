from __future__ import annotations

import unittest
from pathlib import Path


class ForgejoHiddenLifecycleWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = Path(
            ".github/workflows/forgejo-hidden-lifecycle-consume.yml"
        ).read_text(encoding="utf-8")

    def test_exact_frozen_artifact_is_preregistered(self) -> None:
        for value in (
            'FREEZE_RUN_ID: "30760265324"',
            'FREEZE_ARTIFACT_ID: "8837641697"',
            "sha256:eec0beb4dfb2853e6c373d2665fb34f298c7758736c2ebd6b59f066f8607c6c2",
            "af0b76c6a5d34cbe5a0882dfd00ff37f75fbf9c3",
            "44aac0bb90805e7c0889f44d388a752a7513c7b9b7d24433b525a75bd932bb6c",
        ):
            self.assertIn(value, self.text)

    def test_provider_credentials_appear_only_after_bundle_verification(self) -> None:
        verify = self.text.index(
            "Decrypt and verify before provider credentials exist"
        )
        provider = self.text.index(
            "Select one provider before hidden task access"
        )
        key = self.text.index("secrets.BAILIAN_API_KEY")
        self.assertLess(verify, provider)
        self.assertGreater(key, provider)
        self.assertNotIn("BAILIAN_API_KEY", self.text[:provider])
        self.assertNotIn("ZHIPU_CODING_API_KEY", self.text[:provider])

    def test_zhipu_is_a_pre_access_fallback_not_a_midrun_switch(self) -> None:
        selection = self.text.index(
            "Select one provider before hidden task access"
        )
        consume = self.text.index(
            "Consume frozen instance with one ordinary model evaluation"
        )
        section = self.text[selection:consume]
        self.assertIn("open.bigmodel.cn/api/coding/paas/v4", section)
        self.assertIn("probe_provider", section)
        self.assertNotIn("ZHIPU", self.text[consume:])

    def test_evaluation_is_not_an_execution_control(self) -> None:
        consume = self.text.index(
            "Consume frozen instance with one ordinary model evaluation"
        )
        receipt = self.text.index("Build non-sensitive lifecycle receipt")
        section = self.text[consume:receipt]
        self.assertIn("run-native-model", section)
        self.assertNotIn("--execution-control", section)
        self.assertIn("--expected-execution-control false", section)
        self.assertIn("--hidden-finalize", section)
        self.assertIn("record_progress", section)
        self.assertIn("active_variant_ordinal", section)

    def test_public_artifact_contains_no_plaintext_private_directory(self) -> None:
        upload = self.text.index(
            "Upload public receipt and encrypted audit bundle only"
        )
        purge = self.text.index("Purge plaintext hidden state and runtime")
        section = self.text[upload:purge]
        self.assertIn("forgejo-hidden-consume/public/", section)
        self.assertNotIn("forgejo-hidden-consume/private/", section)

    def test_frozen_source_revision_is_used_for_model_execution(self) -> None:
        self.assertIn("git worktree add --detach", self.text)
        build = self.text.index("Build pinned Forgejo runtime")
        start = self.text.index(
            "Start empty stack required by native bundle restore"
        )
        consume = self.text.index(
            "Consume frozen instance with one ordinary model evaluation"
        )
        self.assertLess(build, start)
        self.assertLess(start, consume)
        self.assertIn("manage_forgejo_stack.py up", self.text[start:consume])
        self.assertIn('cd "$source_root"', self.text[consume:])
        self.assertIn("recover_forgejo_evaluation_credentials.py", self.text)


if __name__ == "__main__":
    unittest.main()
