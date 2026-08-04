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

    def test_safe_receipt_is_registered_only_after_hidden_bundle_sealing(self) -> None:
        seal = self.text.index("Seal an unseen private bundle")
        register = self.text.index("Register a safe frozen-hidden receipt")
        self.assertLess(seal, register)
        self.assertIn("contents: write", self.text)
        self.assertIn("data/frozen_hidden_candidates.json", self.text)
        self.assertIn("sealed-bundle.json", self.text)

    def test_missing_secret_generates_an_unseen_private_instance(self) -> None:
        self.assertIn(
            "generate_forgejo_publication_hidden_instance.py",
            self.text,
        )
        self.assertIn('write_bootstrap_status "instance_generated"', self.text)
        self.assertNotIn('write_bootstrap_status "secret_missing"', self.text)
        self.assertIn('"$run_root/private/logs"', self.text)

    def test_checkout_keeps_history_needed_by_novelty_proofs(self) -> None:
        checkout = self.text.index("uses: actions/checkout@v4")
        materialize = self.text.index(
            "Materialize private candidate without model credentials"
        )
        self.assertIn("fetch-depth: 0", self.text[checkout:materialize])

    def test_same_slot_reruns_cancel_stale_freezes(self) -> None:
        self.assertIn(
            "group: forgejo-publication-candidate-${{ github.ref }}",
            self.text,
        )
        self.assertIn("cancel-in-progress: true", self.text)

    def test_manual_freeze_can_seal_an_unseen_bundle_without_a_model(self) -> None:
        seal = self.text.index(
            "Seal an unseen private bundle for later evaluation"
        )
        upload = self.text.index(
            "Upload commitment and aggregate only"
        )
        section = self.text[seal:upload]
        self.assertIn("github.event_name == 'push' ||", section)
        self.assertIn("!inputs.run_execution_control", section)
        self.assertIn("secrets.HIDDEN_BUNDLE_ENCRYPTION_KEY", section)
        self.assertIn("verify_hidden_test_eligibility.py", section)
        self.assertIn("hidden-bundle.tar.gz.enc", section)
        self.assertIn("frozen_unseen", section)
        self.assertIn("ciphertext_sha256", section)
        self.assertNotIn("run-native-model", section)

    def test_only_ciphertext_and_public_metadata_leave_the_runner(self) -> None:
        seal = self.text.index(
            "Seal an unseen private bundle for later evaluation"
        )
        upload = self.text.index(
            "Upload commitment and aggregate only"
        )
        purge = self.text.index("Purge all private state")
        self.assertIn("openssl enc", self.text[seal:upload])
        self.assertIn("rm -f \"$archive\"", self.text[seal:upload])
        self.assertIn("retention-days: 90", self.text[upload:purge])
        self.assertNotIn("private/", self.text[upload:purge])

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

    def test_candidate_push_freezes_without_consuming_the_hidden_instance(self) -> None:
        self.assertIn("forgejo-publication-candidate", self.text)
        self.assertIn("forgejo-publication-hidden-test-002", self.text)
        self.assertIn(
            "github.event_name == 'workflow_dispatch' && inputs.run_execution_control",
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
        self.assertIn("instance_id:", self.text)
        self.assertIn(
            "SELECTED_INSTANCE_ID",
            self.text,
        )

    def test_bootstrap_artifact_reports_only_a_non_sensitive_phase(self) -> None:
        self.assertIn("bootstrap-status.json", self.text)
        self.assertIn('"phase":"%s"', self.text)
        self.assertIn("::notice::bootstrap_phase=%s", self.text)
        self.assertNotIn('cat "$run_root/private/instance.json"', self.text)

    def test_private_reports_and_model_diagnostics_are_not_logged(self) -> None:
        for fragment in (
            'private/logs/prefix.log" 2>&1',
            'private/logs/unit-tests.log" 2>&1',
            'private/logs/$variant-boundary.log',
            'private/logs/$variant-reference.log',
            'private/logs/$baseline-$variant.log" 2>&1',
            'private/logs/admission.log" 2>&1',
            'RUNNER_TEMP/forgejo-hidden-eligibility.log" 2>&1',
            'RUNNER_TEMP/forgejo-pre-provider-freeze-check.log" 2>&1',
            'private/control/repetition-01/$variant.log" 2>&1',
            'private/control/summary.log" 2>&1',
            'private/control/gate.log" 2>&1',
        ):
            self.assertIn(fragment, self.text)

    def test_native_replay_failure_has_a_redacted_diagnostic(self) -> None:
        self.assertIn("Forgejo hidden replay failed", self.text)
        self.assertIn("exception_types=", self.text)
        self.assertIn("r'\"failures\"\\s*", self.text)
        self.assertNotIn('cat "$log_path"', self.text)

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

    def test_package_provenance_hidden_slots_reuse_the_safe_lifecycle(self) -> None:
        for token in (
            "forgejo-package-provenance-hidden-test-001",
            "forgejo-package-provenance-hidden-test-002",
            "build_forgejo_package_provenance_prefix.py",
            "build_forgejo_package_provenance_admission.py",
            "run_forgejo_package_provenance_boundary.py",
        ):
            self.assertIn(token, self.text)

    def test_admission_rejection_emits_a_redacted_gate_summary(self) -> None:
        admission = self.text.index("Admit and freeze before any provider request")
        diagnostic = self.text.index("Record safe native-admission rejection")
        model = self.text.index("Lock and run execution control on frozen state")
        section = self.text[admission:model]
        self.assertIn('if python "$admission_script"', section)
        self.assertIn("write_safe_admission_failure", section)
        self.assertIn("Native admission failed", section)
        self.assertLess(admission, diagnostic)
        self.assertIn("${{ failure() }}", self.text[diagnostic:model])
        self.assertIn("data/evidence/admission-diagnostics", self.text[diagnostic:model])
        self.assertIn("raw_log_published", self.text[diagnostic:model])
        self.assertIn("failure_phase=freeze_native_bundle", section)
        self.assertIn("failure_phase=verify_hidden_test_eligibility", section)
        self.assertIn("diagnostic_status", section)
        self.assertIn('"exit_code"', section)
        self.assertIn('"log_present"', section)
        self.assertIn('"log_sha256"', section)
        self.assertIn("bootstrap-failure.json", self.text[diagnostic:model])
        self.assertIn("failed_tests", self.text)
        self.assertNotIn("private/logs/admission.log\" \"$output", self.text)


if __name__ == "__main__":
    unittest.main()
