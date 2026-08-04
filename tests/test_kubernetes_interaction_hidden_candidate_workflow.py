from __future__ import annotations

import unittest
from pathlib import Path


class KubernetesInteractionHiddenCandidateWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (Path(__file__).resolve().parents[1] / ".github" / "workflows" /
                     "kubernetes-interaction-hidden-candidate.yml").read_text(
                         encoding="utf-8"
                     )

    def test_generates_private_instance_and_registers_only_after_admission(self) -> None:
        self.assertIn("generate_kubernetes_interaction_hidden_instance.py", self.text)
        self.assertIn("$RUNNER_TEMP/kubernetes-hidden", self.text)
        self.assertIn("--benchmark-split hidden_test", self.text)
        self.assertLess(
            self.text.index("build_kubernetes_interaction_admission.py"),
            self.text.index("freeze_native_bundle.py"),
        )
        self.assertLess(
            self.text.index("freeze_native_bundle.py"),
            self.text.index("register frozen receipt"),
        )

    def test_never_publishes_plaintext_private_bundle(self) -> None:
        self.assertIn("HIDDEN_BUNDLE_ENCRYPTION_KEY", self.text)
        self.assertIn("hidden-bundle.tar.gz.enc", self.text)
        self.assertIn("rm -rf \"$RUNNER_TEMP/kubernetes-hidden\"", self.text)
        upload = self.text[self.text.index("Upload safe aggregate evidence only"):]
        self.assertIn("/public/", upload)
        self.assertNotIn("/private/", upload)
        self.assertNotIn("AFTERMATH_API_KEY", self.text)


if __name__ == "__main__":
    unittest.main()
