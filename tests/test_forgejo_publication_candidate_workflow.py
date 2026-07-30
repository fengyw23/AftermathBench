from __future__ import annotations

import unittest
from pathlib import Path


class ForgejoPublicationCandidateWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = Path(
            ".github/workflows/forgejo-publication-candidate.yml"
        ).read_text(encoding="utf-8")

    def test_private_spec_is_secret_and_raw_bundle_is_not_uploaded(self) -> None:
        self.assertIn(
            "secrets.FORGEJO_PUBLICATION_HIDDEN_INSTANCE_B64",
            self.text,
        )
        upload = self.text.index("Upload commitment and aggregate only")
        self.assertIn(
            "${{ runner.temp }}/forgejo-candidate/public/",
            self.text[upload:],
        )
        self.assertNotIn(
            "${{ runner.temp }}/forgejo-candidate/private/",
            self.text[upload:],
        )

    def test_freeze_precedes_step_scoped_model_credential(self) -> None:
        freeze = self.text.index(
            "Admit and freeze before any provider request"
        )
        model = self.text.index(
            "Lock and run execution control on frozen state"
        )
        api_key = self.text.index(
            "AFTERMATH_API_KEY: ${{ secrets.BAILIAN_API_KEY }}"
        )

        self.assertLess(freeze, model)
        self.assertGreater(api_key, model)
        job_env = self.text[
            self.text.index("env:", self.text.index("jobs:")) : freeze
        ]
        self.assertNotIn("BAILIAN_API_KEY", job_env)

    def test_reference_baselines_and_model_share_exact_state_bundles(self) -> None:
        self.assertIn("snapshot-bundle", self.text)
        self.assertGreaterEqual(self.text.count("restore-bundle"), 3)
        self.assertIn("freeze_native_bundle.py", self.text)
        self.assertIn("--hidden-freeze", self.text)
        self.assertIn("--hidden-usage-ledger", self.text)

    def test_candidate_branch_runs_the_default_execution_control(self) -> None:
        self.assertIn("forgejo-publication-candidate", self.text)
        self.assertIn(
            "github.event_name == 'push' || inputs.run_execution_control",
            self.text,
        )
        self.assertIn("inputs.model || 'glm-5.2'", self.text)

    def test_candidate_runtime_owner_comes_from_private_spec(self) -> None:
        self.assertIn(
            'json.load(open(sys.argv[1]))["owner"]',
            self.text,
        )
        self.assertIn('--username "$owner"', self.text)

    def test_private_identity_overlap_is_rejected_before_rendering(self) -> None:
        novelty = self.text.index(
            "verify_forgejo_instance_novelty.py"
        )
        rendering = self.text.index(
            "render_forgejo_publication_blueprint.py"
        )
        self.assertLess(novelty, rendering)
        self.assertIn("--instance-id candidate-001", self.text)

    def test_private_reports_and_model_diagnostics_are_not_logged(self) -> None:
        for fragment in (
            'private/logs/prefix.log" 2>&1',
            'private/logs/$variant-boundary.log" 2>&1',
            'private/logs/$variant-reference.log" 2>&1',
            'private/logs/$baseline-$variant.log" 2>&1',
            'private/logs/admission.log" 2>&1',
            'RUNNER_TEMP/forgejo-hidden-eligibility.log" 2>&1',
            'RUNNER_TEMP/forgejo-pre-provider-freeze-check.log" 2>&1',
            'private/control/repetition-01/$variant.log" 2>&1',
            'private/control/summary.log" 2>&1',
            'private/control/gate.log" 2>&1',
        ):
            self.assertIn(fragment, self.text)

    def test_execution_control_has_an_explicit_acceptance_gate(self) -> None:
        self.assertIn("validate_native_control_summary.py", self.text)
        self.assertIn("--minimum-pass-rate 0.8", self.text)
        self.assertIn("--hidden-evaluation-id", self.text)
        self.assertIn("--hidden-finalize", self.text)
        self.assertNotIn("record_native_bundle_usage.py", self.text)

    def test_frozen_bundle_is_reverified_before_model_access(self) -> None:
        verification = self.text.index("verify_frozen_bundle.py")
        model_call = self.text.index("run-native-model")
        self.assertLess(verification, model_call)


if __name__ == "__main__":
    unittest.main()
