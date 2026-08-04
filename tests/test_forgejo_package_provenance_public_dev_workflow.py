import unittest

from aftermath_bench.schema import repository_root


class ForgejoPackageProvenancePublicDevWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = (
            repository_root()
            / ".github"
            / "workflows"
            / "forgejo-package-provenance-public-dev-candidate.yml"
        )
        cls.text = cls.path.read_text(encoding="utf-8")

    def test_candidate_uses_fresh_spec_and_bound_blueprint(self) -> None:
        self.assertIn("forgejo-package-provenance-public-*.json", self.text)
        self.assertIn("verify_forgejo_instance_novelty.py", self.text)
        self.assertIn("render_forgejo_package_provenance_blueprint.py", self.text)
        self.assertIn('cmp "$blueprint"', self.text)

    def test_candidate_replays_references_baselines_and_strict_admission(self) -> None:
        self.assertIn("run_forgejo_package_provenance_boundary.py", self.text)
        self.assertIn("run_forgejo_package_provenance_control.py", self.text)
        self.assertIn("run_forgejo_package_provenance_baseline.py", self.text)
        self.assertIn("build_forgejo_package_provenance_admission.py", self.text)
        self.assertIn("validate-native-scenario", self.text)

    def test_hidden_candidate_uses_nonmonotonic_r2_boundaries(self) -> None:
        hidden = (
            repository_root()
            / ".github"
            / "workflows"
            / "forgejo-publication-candidate.yml"
        ).read_text(encoding="utf-8")
        package_block = hidden.split(
            'if [ "$SELECTED_FAMILY" = package_provenance ]', 1
        )[1].split("else", 1)[0]
        self.assertIn("--generation r2", package_block)
        self.assertIn("build_forgejo_package_provenance_admission.py", hidden)


if __name__ == "__main__":
    unittest.main()
