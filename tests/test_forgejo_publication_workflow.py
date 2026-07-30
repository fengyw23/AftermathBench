from __future__ import annotations

import unittest

from aftermath_bench.integrations.forgejo_publication_baselines import (
    PUBLICATION_BASELINE_NAMES,
)
from aftermath_bench.integrations.forgejo_publication_faults import (
    FORGEJO_PUBLICATION_VARIANTS,
)
from aftermath_bench.schema import repository_root


class ForgejoPublicationWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (
            repository_root()
            / ".github"
            / "workflows"
            / "forgejo-publication-runtime.yml"
        ).read_text(encoding="utf-8")

    def test_replays_every_variant_and_fixed_policy(self) -> None:
        for variant in FORGEJO_PUBLICATION_VARIANTS:
            self.assertIn(variant, self.text)
        for baseline in PUBLICATION_BASELINE_NAMES:
            self.assertIn(baseline, self.text)
        self.assertIn(
            "build_forgejo_publication_admission.py", self.text
        )
        self.assertIn("validate-native-scenario", self.text)

    def test_builds_pinned_source_and_sanitizes_credentials(self) -> None:
        self.assertIn("build_forgejo_runtime.py", self.text)
        self.assertIn("--checkout", self.text)
        self.assertIn("--build", self.text)
        self.assertIn(
            'rm -f "$runtime_root/credentials.json"', self.text
        )
        self.assertNotIn("AFTERMATH_API_KEY", self.text)


if __name__ == "__main__":
    unittest.main()
