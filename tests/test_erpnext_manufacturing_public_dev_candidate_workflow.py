from __future__ import annotations

import unittest
from pathlib import Path


class ERPNextManufacturingPublicDevCandidateWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = Path(
            ".github/workflows/erpnext-manufacturing-public-dev-candidate.yml"
        ).read_text(encoding="utf-8")

    def test_instance_is_rendered_and_hash_bound_before_runtime_build(self) -> None:
        self.assertIn("fetch-depth: 0", self.text)
        self.assertIn("render_erpnext_native_blueprint.py", self.text)
        self.assertIn("instance_spec_sha256", self.text)
        self.assertLess(
            self.text.index("Render and verify the instance-bound blueprint"),
            self.text.index("Build pinned ERPNext and the native prefix"),
        )

    def test_all_four_boundaries_are_replayed_with_references(self) -> None:
        for variant in (
            "request_not_reached",
            "database_committed_response_lost",
            "after_commit_enqueue_failed",
            "async_job_pending",
        ):
            self.assertIn(variant, self.text)
        self.assertIn("run_erpnext_manufacturing_failure.py", self.text)
        self.assertIn("run_erpnext_manufacturing_control.py", self.text)
        self.assertIn("capture_erpnext_manufacturing_state_evidence.py", self.text)

    def test_public_artifact_excludes_database_and_credentials(self) -> None:
        upload = self.text[self.text.index("name: erpnext-manufacturing-public-dev-002-") :]
        self.assertNotIn("bundles/", upload)
        self.assertNotIn("credentials.json", upload)
        self.assertIn('rm -rf "$RUN_ROOT/bundles"', self.text)

    def test_admission_is_replay_derived_and_secret_free(self) -> None:
        self.assertIn("build_erpnext_manufacturing_admission.py", self.text)
        self.assertIn("validate-native-scenario", self.text)
        self.assertIn("verify_public_evidence_safe.py", self.text)
        self.assertNotIn("AFTERMATH_API_KEY", self.text)


if __name__ == "__main__":
    unittest.main()
