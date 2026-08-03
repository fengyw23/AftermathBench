from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class ForgejoPackageProvenanceModelWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (
            repository_root()
            / ".github"
            / "workflows"
            / "forgejo-package-provenance-model.yml"
        ).read_text(encoding="utf-8")

    def test_reuses_one_native_prefix_for_both_models(self) -> None:
        self.assertEqual(
            self.text.count("build_forgejo_package_provenance_prefix.py"),
            1,
        )
        self.assertIn("package-prefix.tar.gz", self.text)
        self.assertIn("glm-5.2", self.text)
        self.assertIn("DeepSeek-V4-Pro", self.text)

    def test_runs_the_exact_admitted_matched_group(self) -> None:
        for variant in (
            "package_request_not_reached",
            "package_binary_committed_response_lost",
            "package_complete_index_missing",
            "package_complete_index_accepted_response_lost",
        ):
            self.assertIn(variant, self.text)
        self.assertIn(
            "data/scenarios/forgejo-package-provenance-public-dev-001/scenario.json",
            self.text,
        )

    def test_r2_selects_the_nonmonotonic_instance_and_matched_group(self) -> None:
        self.assertIn("generation:", self.text)
        self.assertIn("GENERATION: ${{ inputs.generation || 'r1' }}", self.text)
        self.assertIn(
            "data/instance_specs/"
            "forgejo-package-provenance-nonmonotonic-dev-001.json",
            self.text,
        )
        self.assertIn(
            "data/scenarios/"
            "forgejo-package-provenance-nonmonotonic-dev-001/scenario.json",
            self.text,
        )
        self.assertIn('--scenario "$scenario"', self.text)
        self.assertNotIn('--scenario "$SCENARIO"\n', self.text)
        for variant in (
            "r2_package_request_not_reached",
            "r2_package_binary_committed_response_lost",
            "r2_package_complete_index_missing",
            "r2_package_corrupt_binary_index_missing",
        ):
            self.assertIn(variant, self.text)
        self.assertIn('echo "generation=$GENERATION"', self.text)

    def test_secrets_are_selected_without_being_artifacts(self) -> None:
        self.assertIn("secrets.BAILIAN_API_KEY", self.text)
        self.assertIn("secrets.PARATERA_API_KEY", self.text)
        self.assertIn('echo "::add-mask::$api_key"', self.text)
        upload = self.text.split("Upload complete public trajectories", 1)[1]
        self.assertNotIn("credentials.json", upload.split("Purge native services", 1)[0])

    def test_execution_control_has_a_strict_acceptance_gate(self) -> None:
        self.assertIn("validate_native_control_summary.py", self.text)
        self.assertIn("--expected-cases 4", self.text)
        self.assertIn("--minimum-pass-rate 0.8", self.text)


if __name__ == "__main__":
    unittest.main()
