from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class ForgejoReconciliationWorkflowTest(unittest.TestCase):
    def test_runtime_replays_every_independent_gap_and_audits_depth(self) -> None:
        text = (
            repository_root()
            / ".github"
            / "workflows"
            / "forgejo-reconciliation-runtime.yml"
        ).read_text(encoding="utf-8")
        for variant in (
            "all_effects_valid_response_lost",
            "actions_bundle_missing",
            "artifact_registry_missing",
            "production_deployment_missing",
            "external_attestation_missing",
            "release_metadata_missing",
        ):
            self.assertIn(variant, text)
        self.assertIn("run_forgejo_reconciliation_boundary.py", text)
        self.assertIn("run_forgejo_reconciliation_reference.py", text)
        self.assertIn("audit_forgejo_reconciliation_runtime.py", text)
        self.assertIn("restore-promotion-bundle", text)


if __name__ == "__main__":
    unittest.main()
