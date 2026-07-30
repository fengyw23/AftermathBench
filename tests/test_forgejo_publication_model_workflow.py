from __future__ import annotations

import unittest
from pathlib import Path

from aftermath_bench.integrations.forgejo_publication_faults import (
    FORGEJO_PUBLICATION_VARIANTS,
)


class ForgejoPublicationModelWorkflowTests(unittest.TestCase):
    def test_workflow_runs_every_matched_boundary_with_bailian(self) -> None:
        text = Path(
            ".github/workflows/forgejo-publication-model.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("secrets.BAILIAN_API_KEY", text)
        self.assertIn("glm-5.2", text)
        self.assertIn("forgejo-publication-model-control", text)
        self.assertIn("forgejo-publication-model-eval", text)
        self.assertIn(
            "data/scenarios/forgejo-release-publication-dev-002/"
            "scenario.json",
            text,
        )
        self.assertIn("validate-native-scenario", text)
        self.assertIn("--max-turns 25", text)
        self.assertIn("--expected-execution-control", text)
        for variant in FORGEJO_PUBLICATION_VARIANTS:
            self.assertIn(variant, text)

    def test_boundary_is_rebuilt_after_every_snapshot_restore(self) -> None:
        text = Path(
            ".github/workflows/forgejo-publication-model.yml"
        ).read_text(encoding="utf-8")
        restore = text.index("manage_forgejo_stack.py restore")
        boundary = text.index("run_forgejo_publication_boundary.py")
        model = text.index("run-native-model", boundary)

        self.assertLess(restore, boundary)
        self.assertLess(boundary, model)
