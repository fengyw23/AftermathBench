from __future__ import annotations

import unittest
from pathlib import Path

from aftermath_bench.integrations.forgejo_publication_faults import (
    FORGEJO_PUBLICATION_VARIANTS,
)
from aftermath_bench.integrations.forgejo_publication_instance import (
    ForgejoPublicationInstanceSpec,
)
from scripts.verify_forgejo_instance_novelty import (
    find_overlaps,
    novelty_scan_paths,
    tracked_paths,
)


class ForgejoPublicationPublicDevWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = Path(
            ".github/workflows/forgejo-publication-public-dev.yml"
        ).read_text(encoding="utf-8")

    def test_trigger_and_public_identity_are_explicit(self) -> None:
        self.assertIn("forgejo-publication-public-dev", self.text)
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn(
            "public-dev-slot-002.json",
            self.text,
        )
        self.assertIn("--instance-id dev-002", self.text)
        self.assertIn("--benchmark-split public_dev", self.text)

    def test_novelty_and_rendered_blueprint_are_checked_first(self) -> None:
        novelty = self.text.index("verify_forgejo_instance_novelty.py")
        render = self.text.index("render_forgejo_publication_blueprint.py")
        source_build = self.text.index("build_forgejo_runtime.py")
        self.assertLess(novelty, render)
        self.assertLess(render, source_build)
        self.assertIn('--bound-blueprint "$BLUEPRINT"', self.text)
        self.assertIn(
            'cmp "$BLUEPRINT" "$RUN_ROOT/rendered-blueprint.json"',
            self.text,
        )

    def test_committed_workflow_does_not_leak_instance_identity(self) -> None:
        root = Path.cwd()
        instance_path = root / "data/instance_specs/public-dev-slot-002.json"
        blueprint_path = (
            root / "data/scenario_blueprints/public-dev-slot-002/scenario.json"
        )
        instance = ForgejoPublicationInstanceSpec.from_path(instance_path)
        scan_paths = novelty_scan_paths(
            tracked_paths(root),
            instance_spec_path=instance_path,
            instance=instance,
            bound_blueprint_path=blueprint_path,
        )
        self.assertEqual(
            find_overlaps(instance.as_dict(), scan_paths),
            [],
        )

    def test_reset_and_boundary_evidence_bind_exact_state_bundles(self) -> None:
        prefix_snapshot = self.text.index(
            'snapshot-bundle \\\n            --snapshot "$NATIVE_ROOT/bundles/prefix"'
        )
        establishment = self.text.index("--establish-expected-projection")
        boundary_step = self.text.index(
            "Capture eight exact boundaries and replay references"
        )
        reset_capture = self.text.index("--phase reset", boundary_step)
        boundary_call = self.text.index(
            "run_forgejo_publication_boundary.py", reset_capture
        )
        boundary_snapshot = self.text.index("snapshot-bundle", boundary_call)
        boundary_capture = self.text.index("--phase boundary", boundary_snapshot)
        reference_restore = self.text.index("restore-bundle", boundary_capture)
        reference_recapture = self.text.index(
            "capture_forgejo_publication_state_evidence.py",
            reference_restore,
        )
        reference_compare = self.text.index(
            'cmp "$boundary_evidence" "$reference_start"',
            reference_recapture,
        )
        reference = self.text.index(
            "run_forgejo_publication_control.py",
            reference_compare,
        )

        self.assertLess(prefix_snapshot, establishment)
        self.assertLess(establishment, reset_capture)
        self.assertLess(reset_capture, boundary_call)
        self.assertLess(boundary_call, boundary_snapshot)
        self.assertLess(boundary_snapshot, boundary_capture)
        self.assertLess(boundary_capture, reference_restore)
        self.assertLess(reference_restore, reference_recapture)
        self.assertLess(reference_recapture, reference_compare)
        self.assertLess(reference_compare, reference)
        self.assertLess(reference_restore, reference)
        self.assertIn(
            '--expected-projection "$NATIVE_ROOT/expected-reset-projection.json"',
            self.text,
        )
        self.assertIn('--reset-evidence "$reset_evidence"', self.text)
        self.assertIn(
            '--failure-report "$NATIVE_ROOT/runtime/$variant-boundary.json"',
            self.text,
        )
        self.assertIn(
            "$variant-reference-start.json",
            self.text[reference_restore:reference],
        )

    def test_native_replay_failure_identifies_variant_and_emits_log(self) -> None:
        self.assertIn("run_logged() {", self.text)
        self.assertIn(
            'echo "::group::capture-and-reference $variant"',
            self.text,
        )
        self.assertIn(
            'echo "::error::native replay command failed; captured log follows"',
            self.text,
        )
        self.assertIn('cat "$log_path"', self.text)
        self.assertIn(
            'echo "::error::reference start differs from admitted boundary"',
            self.text,
        )

    def test_admission_failure_surfaces_its_captured_log(self) -> None:
        admission = self.text.index(
            "Admit the active scenario and freeze the native evidence bundle"
        )
        formal_lock = self.text.index(
            "Freeze the five formal input roles before provider access"
        )
        section = self.text[admission:formal_lock]
        self.assertIn(
            "::error::admission command failed; captured log follows",
            section,
        )
        self.assertIn(
            'run_logged "$RUN_ROOT/logs/admission.log"',
            section,
        )
        self.assertIn(
            'run_logged "$RUN_ROOT/logs/scenario-validation.log"',
            section,
        )
        self.assertIn(
            'run_logged "$RUN_ROOT/logs/native-files.log"',
            section,
        )
        self.assertIn('cat "$log_path"', section)

    def test_all_consumers_restore_the_same_boundary_bundle(self) -> None:
        reference_section = self.text[
            self.text.index("Capture eight exact boundaries") : self.text.index(
                "Execute every fixed policy"
            )
        ]
        baseline_section = self.text[
            self.text.index("Execute every fixed policy") : self.text.index(
                "Admit the active scenario"
            )
        ]
        control_section = self.text[
            self.text.index("Run execution controls") : self.text.index(
                "Complete and validate"
            )
        ]
        exact_boundary = '"$NATIVE_ROOT/bundles/boundary-$variant"'
        self.assertIn(exact_boundary, reference_section)
        self.assertIn(exact_boundary, baseline_section)
        self.assertIn(exact_boundary, control_section)
        self.assertNotIn(
            "run_forgejo_publication_boundary.py",
            baseline_section,
        )
        self.assertNotIn(
            "run_forgejo_publication_boundary.py",
            control_section,
        )

    def test_control_recaptures_and_compares_live_state_before_provider(
        self,
    ) -> None:
        section = self.text[
            self.text.index("Run execution controls") : self.text.index(
                "Complete and validate"
            )
        ]
        restore = section.index("restore-bundle")
        capture = section.index(
            "capture_forgejo_publication_state_evidence.py",
            restore,
        )
        compare = section.index(
            '"$NATIVE_ROOT/runtime/state-evidence/$variant-boundary.json"',
            capture,
        )
        model = section.index("run-native-model", compare)
        self.assertLess(restore, capture)
        self.assertLess(capture, compare)
        self.assertLess(compare, model)
        self.assertIn("--phase boundary", section[capture:model])
        self.assertIn(
            '--output "$pre_model_capture"',
            section[capture:model],
        )
        self.assertIn('"$pre_model_capture"', section[compare:model])
        self.assertIn(
            '--pre-model-boundary-evidence "$pre_model_capture"',
            section[model:],
        )

    def test_each_baseline_recaptures_and_compares_its_live_start(self) -> None:
        section = self.text[
            self.text.index("Execute every fixed policy") : self.text.index(
                "Admit the active scenario"
            )
        ]
        restore = section.index("restore-bundle")
        capture = section.index(
            "capture_forgejo_publication_state_evidence.py",
            restore,
        )
        compare = section.index("cmp", capture)
        baseline = section.index(
            "run_forgejo_publication_baseline.py",
            compare,
        )
        self.assertLess(restore, capture)
        self.assertLess(capture, compare)
        self.assertLess(compare, baseline)
        self.assertIn(
            "$NATIVE_ROOT/baselines/pre-state/$baseline-$variant.json",
            section,
        )

    def test_hard_admission_and_exact_manifest_precede_input_lock(self) -> None:
        admission = self.text.index("build_forgejo_publication_admission.py")
        validation = self.text.index("validate-native-scenario", admission)
        source_verification = self.text.index(
            '"$NATIVE_ROOT/runtime/source-verification.json"',
            validation,
        )
        manifest = self.text.index(
            '--output "$NATIVE_ROOT/files.json"',
            source_verification,
        )
        input_spec = self.text.index("generate_forgejo_formal_build_spec.py", manifest)
        input_build = self.text.index("build_formal_evidence.py", input_spec)
        model = self.text.index("run-native-model", input_build)
        self.assertLess(admission, validation)
        self.assertLess(validation, source_verification)
        self.assertLess(source_verification, manifest)
        self.assertLess(manifest, input_spec)
        self.assertLess(input_spec, input_build)
        self.assertLess(input_build, model)
        self.assertIn("--phase inputs", self.text[input_spec:model])
        self.assertIn("formal-input-lock.json", self.text[input_build:model])

    def test_active_scenario_is_rebuilt_then_compared_or_atomically_installed(
        self,
    ) -> None:
        section = self.text[
            self.text.index("Admit the active scenario") : self.text.index(
                "Freeze the five formal input roles"
            )
        ]
        self.assertIn(
            '--output-directory "$RUN_ROOT/scenario-staging"',
            section,
        )
        self.assertIn(
            '--scenario "$RUN_ROOT/scenario-staging/scenario.json"',
            section,
        )
        self.assertIn('if [ -d "$SCENARIO_DIRECTORY" ]', section)
        self.assertIn("diff --recursive", section)
        self.assertIn(
            'mv "$RUN_ROOT/scenario-staging" "$SCENARIO_DIRECTORY"',
            section,
        )
        first_step = self.text[
            self.text.index("Verify and materialize") : self.text.index(
                "Build pinned Forgejo"
            )
        ]
        self.assertNotIn('test ! -e "$SCENARIO_DIRECTORY"', first_step)

    def test_active_scenario_path_is_derived_from_validated_identity(
        self,
    ) -> None:
        section = self.text[
            self.text.index("Admit the active scenario") : self.text.index(
                "Freeze the five formal input roles"
            )
        ]
        validation = section.index("validate-native-scenario")
        derivation = section.index('scenario_id="$(', validation)
        canonical_path = section.index(
            'SCENARIO_DIRECTORY="data/scenarios/$scenario_id"',
            derivation,
        )
        persistence = section.index('>> "$GITHUB_ENV"', canonical_path)
        installation = section.index(
            'mv "$RUN_ROOT/scenario-staging" "$SCENARIO_DIRECTORY"',
            persistence,
        )
        self.assertLess(validation, derivation)
        self.assertLess(derivation, canonical_path)
        self.assertLess(canonical_path, persistence)
        self.assertLess(persistence, installation)
        self.assertIn(
            're.fullmatch(r"[a-z0-9][a-z0-9._-]*", value)',
            section,
        )
        job_environment = self.text[
            self.text.index("    env:") : self.text.index("    steps:")
        ]
        self.assertNotIn("SCENARIO_DIRECTORY:", job_environment)

    def test_formal_build_failures_surface_captured_logs(self) -> None:
        input_section = self.text[
            self.text.index("Freeze the five formal input roles"):
            self.text.index("Run execution controls")
        ]
        completion_section = self.text[
            self.text.index("Complete and validate"):
            self.text.index("Seal the public evidence archive")
        ]
        for section, expected in (
            (
                input_section,
                (
                    'run_logged "formal input spec generation"',
                    'run_logged "formal input evidence build"',
                    "::error::formal input lock was not created",
                ),
            ),
            (
                completion_section,
                (
                    'run_logged "control manifest generation"',
                    'run_logged "formal completion spec generation"',
                    'run_logged "formal completion evidence build"',
                    "::error::formal completion declarations were not created",
                ),
            ),
        ):
            self.assertIn("captured log follows", section)
            self.assertIn('cat "$log_path"', section)
            for value in expected:
                self.assertIn(value, section)

    def test_provider_secret_is_step_scoped_after_formal_input_lock(self) -> None:
        lock_step = self.text.index(
            "Freeze the five formal input roles before provider access"
        )
        control_step = self.text.index(
            "Run execution controls from the locked exact boundaries"
        )
        key = self.text.index("AFTERMATH_API_KEY: ${{ secrets.BAILIAN_API_KEY }}")
        model = self.text.index("run-native-model", control_step)
        self.assertLess(lock_step, control_step)
        self.assertGreater(key, control_step)
        self.assertLess(key, model)
        self.assertNotIn("BAILIAN_API_KEY", self.text[:control_step])
        self.assertIn(
            '--formal-input-lock "$FORMAL_OUTPUT/formal-input-lock.json"',
            self.text[control_step:],
        )
        self.assertIn(
            "verify_public_evidence_safe.py",
            self.text[control_step:],
        )
        self.assertIn("--secret-env AFTERMATH_API_KEY", self.text[control_step:])

    def test_missing_control_trajectory_is_retried_from_locked_boundary(
        self,
    ) -> None:
        section = self.text[
            self.text.index("Run execution controls"):
            self.text.index("Complete and validate")
        ]
        self.assertIn("restore_and_capture_boundary()", section)
        self.assertIn("run_control_once()", section)
        self.assertIn("valid_trajectory()", section)
        self.assertIn(
            "validate_native_control_trajectory.py",
            section,
        )
        self.assertIn(
            "produced no valid trajectory; retrying once from the locked boundary",
            section,
        )
        self.assertIn(
            "produced no valid trajectory after one retry",
            section,
        )
        self.assertGreaterEqual(
            section.count('restore_and_capture_boundary "$variant"'),
            2,
        )
        self.assertNotIn('cat "$first_log"', section)
        self.assertNotIn('cat "$retry_log"', section)

    def test_all_variants_and_strict_control_gate_are_bound(self) -> None:
        self.assertIn('test "${#variants[@]}" -eq 8', self.text)
        for variant in FORGEJO_PUBLICATION_VARIANTS:
            self.assertIn(
                variant,
                Path(
                    "data/scenario_blueprints/"
                    "public-dev-slot-002/scenario.json"
                ).read_text(encoding="utf-8"),
            )
        self.assertIn("--expected-execution-control true", self.text)
        self.assertIn("--expected-cases 8", self.text)
        self.assertIn("--minimum-pass-rate 0.8", self.text)
        self.assertIn(
            '--output "$CONTROL_ROOT/model-runs/summary.json"',
            self.text,
        )

    def test_completion_is_derived_after_control_and_keeps_input_lock(self) -> None:
        control = self.text.index("Run execution controls")
        control_manifest = self.text.index(
            '--output "$CONTROL_ROOT/files.json"', control
        )
        complete_spec = self.text.index(
            "generate_forgejo_formal_build_spec.py", control_manifest
        )
        complete_build = self.text.index("build_formal_evidence.py", complete_spec)
        declarations = self.text.index("completion/declarations.json", complete_build)
        self.assertLess(control, control_manifest)
        self.assertLess(control_manifest, complete_spec)
        self.assertLess(complete_spec, complete_build)
        self.assertLess(complete_build, declarations)
        section = self.text[complete_spec:declarations]
        self.assertIn("--phase complete", section)
        self.assertIn("--control-manifest", section)
        self.assertIn("--model-input-lock", section)
        completion_step = self.text[
            self.text.rindex(
                "- name: Complete and validate",
                0,
                complete_spec,
            ) : complete_spec
        ]
        self.assertIn("if: always()", completion_step)
        self.assertIn("continue-on-error: true", completion_step)

    def test_public_archive_omits_private_restore_bytes_and_credentials(
        self,
    ) -> None:
        seal = self.text.index(
            "Seal the public evidence archive and reject credentials"
        )
        upload = self.text.index("Upload safe public evidence")
        purge = self.text.index("Purge native services", upload)
        archive_section = self.text[seal:purge]
        self.assertIn("credentials.json", archive_section)
        self.assertIn("verify_public_evidence_safe.py", archive_section)
        self.assertIn('--root "$RUN_ROOT"', archive_section)
        self.assertIn(
            "build_forgejo_public_evidence_archive.py",
            archive_section,
        )
        self.assertIn("--expected-restore-bundle-count 9", archive_section)
        self.assertIn(
            '--root "$RUNNER_TEMP/forgejo-public-dev-public"',
            archive_section,
        )
        self.assertIn(
            'if [ ! -f "$RUNNER_TEMP/forgejo-public-dev-provider-scan.ok" ]',
            archive_section,
        )
        self.assertIn(
            "::error::provider-stage safety sentinel is missing",
            archive_section,
        )
        self.assertNotIn(
            'test -s "$FORMAL_OUTPUT/completion/declarations.json"',
            archive_section,
        )
        self.assertIn(
            "build_forgejo_publication_status.py",
            archive_section,
        )
        self.assertNotIn(
            "runtimes/forgejo/.runtime/",
            self.text[upload:purge],
        )
        self.assertNotIn("$RUN_ROOT", self.text[upload:purge])
        self.assertNotIn("forgejo-data.tar.gz", self.text[upload:purge])
        self.assertNotIn(
            "webhook-sink-data.tar.gz",
            self.text[upload:purge],
        )
        self.assertIn(
            "path: ${{ runner.temp }}/forgejo-public-dev-public/",
            self.text[upload:purge],
        )
        self.assertIn("snapshot-bundle", self.text)
        self.assertIn("forgejo-data.tar.gz", self.text)
        self.assertIn("webhook-sink-data.tar.gz", self.text)

    def test_formal_package_has_a_canonical_repo_ready_path(self) -> None:
        self.assertIn(
            "FORMAL_OUTPUT: data/evidence/formal/"
            "aftermathbench-2026.08-r1/forgejo/"
            "forgejo-release-package-publication/dev-002",
            self.text,
        )
        seal = self.text[
            self.text.index("Seal the public evidence archive") : self.text.index(
                "Upload safe public evidence"
            )
        ]
        self.assertIn(
            '"$RUN_ROOT/repo-ready/$FORMAL_OUTPUT"',
            seal,
        )
        self.assertIn(
            '"$RUN_ROOT/repo-ready/$SCENARIO_DIRECTORY"',
            seal,
        )
        self.assertIn(
            'if [ -s "$FORMAL_OUTPUT/completion/declarations.json" ]',
            seal,
        )
        self.assertIn(
            '"$RUN_ROOT/diagnostics/formal-output/"',
            seal,
        )

    def test_upload_is_impossible_when_either_secret_scan_fails(self) -> None:
        provider_scan = self.text.index("--secret-env AFTERMATH_API_KEY")
        sentinel = self.text.index(
            'touch "$RUNNER_TEMP/forgejo-public-dev-provider-scan.ok"',
            provider_scan,
        )
        seal = self.text.index("id: seal", sentinel)
        sentinel_check = self.text.index(
            'if [ ! -f "$RUNNER_TEMP/forgejo-public-dev-provider-scan.ok" ]',
            seal,
        )
        final_scan = self.text.index(
            "verify_public_evidence_safe.py",
            sentinel_check,
        )
        upload = self.text.index("Upload safe public evidence", final_scan)
        upload_gate = self.text.index(
            "if: ${{ always() && steps.seal.outcome == 'success' }}",
            upload,
        )
        self.assertLess(provider_scan, sentinel)
        self.assertLess(sentinel, sentinel_check)
        self.assertLess(sentinel_check, final_scan)
        self.assertLess(final_scan, upload)
        self.assertGreater(upload_gate, upload)

    def test_low_control_score_remains_publishable_diagnostic_evidence(
        self,
    ) -> None:
        controls = self.text[
            self.text.index("Run execution controls") : self.text.index(
                "Complete and validate"
            )
        ]
        self.assertIn(
            "if python scripts/validate_native_control_summary.py",
            controls,
        )
        self.assertNotIn('exit "$run_status"', controls)
        self.assertIn(
            '"$RUN_ROOT/control-collection-status.txt"',
            controls,
        )
        seal = self.text[
            self.text.index("Seal the public evidence archive") : self.text.index(
                "Upload safe public evidence"
            )
        ]
        self.assertIn(
            '--output "$RUN_ROOT/publication-status.json"',
            seal,
        )
        self.assertIn("--minimum-pass-rate 0.8", seal)
        self.assertIn(
            "forgejo-publication-public-dev-evidence-${{ github.run_id }}",
            self.text,
        )
        self.assertNotIn(
            "forgejo-publication-public-dev-formal-${{ github.run_id }}",
            self.text,
        )


if __name__ == "__main__":
    unittest.main()
