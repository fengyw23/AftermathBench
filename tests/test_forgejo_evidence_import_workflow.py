from __future__ import annotations

import unittest
from pathlib import Path


class ForgejoEvidenceImportWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = (
            Path(__file__).parents[1]
            / ".github"
            / "workflows"
            / "forgejo-public-dev-evidence-import.yml"
        )
        cls.text = path.read_text(encoding="utf-8")

    def test_gate_only_trigger_and_no_provider_secret(self) -> None:
        trigger = self.text.split("permissions:", maxsplit=1)[0]
        self.assertIn("forgejo-public-dev-slot-002-evidence-import.json", trigger)
        self.assertNotIn("workflow_dispatch", trigger)
        self.assertNotIn("schedule:", trigger)
        lowered = self.text.lower()
        self.assertNotIn("bailian_api_key", lowered)
        self.assertNotIn("aftermath_api_key", lowered)
        self.assertNotIn("secrets.", lowered)

    def test_import_is_provenance_bound_and_manifest_independent(self) -> None:
        self.assertIn("validate_forgejo_evidence_import.py provenance", self.text)
        self.assertIn("actions/download-artifact@v4", self.text)
        self.assertIn("generate_formal_release_binding.py", self.text)
        self.assertNotIn("data/release_manifest.json", self.text)
        self.assertIn("unexpected file outside Forgejo import allowlist", self.text)


if __name__ == "__main__":
    unittest.main()
