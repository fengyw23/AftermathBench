from __future__ import annotations

import copy
import hashlib
import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.benchmark_matrix import (
    benchmark_family_index,
    load_benchmark_matrix,
)
from aftermath_bench.native_admission import validate_native_scenario
from aftermath_bench.native_freeze import (
    append_usage_event,
    build_frozen_bundle,
)
from aftermath_bench.erpnext_sales_return_state_evidence import (
    canonical_state_fingerprint,
)
from aftermath_bench.native_scenario import NativeScenario, load_native_scenario
from aftermath_bench.release_manifest import (
    FORMAL_EVIDENCE_DEPENDENCIES,
    FORMAL_EVIDENCE_ROLES,
    _invoke_trusted_formal_evaluator,
    _validate_admission_release_binding,
    _validate_control_summary,
    _validate_hidden_bundle,
    _validate_variant_semantics,
    bound_reset_snapshot_sha256,
    default_release_manifest_path,
    derive_release_state,
    file_sha256,
    load_release_manifest,
    validate_formal_evidence_roles,
    validate_release_manifest,
)
from aftermath_bench.schema import repository_root


class ResetSnapshotBindingTests(unittest.TestCase):
    def test_accepts_canonical_or_native_reset_hash_name(self) -> None:
        digest = "a" * 64
        self.assertEqual(
            bound_reset_snapshot_sha256({"reset_snapshot_sha256": digest}),
            digest,
        )
        self.assertEqual(
            bound_reset_snapshot_sha256(
                {"reset_evidence_file_sha256": digest}
            ),
            digest,
        )
        self.assertEqual(
            bound_reset_snapshot_sha256(
                {
                    "reset_snapshot_sha256": digest,
                    "reset_evidence_file_sha256": digest,
                }
            ),
            digest,
        )

    def test_rejects_missing_invalid_or_conflicting_reset_hashes(self) -> None:
        self.assertIsNone(bound_reset_snapshot_sha256({}))
        self.assertIsNone(
            bound_reset_snapshot_sha256(
                {"reset_evidence_file_sha256": "not-a-sha256"}
            )
        )
        self.assertIsNone(
            bound_reset_snapshot_sha256(
                {
                    "reset_snapshot_sha256": "a" * 64,
                    "reset_evidence_file_sha256": "b" * 64,
                }
            )
        )


class TrustedFormalEvaluatorProtocolTests(unittest.TestCase):
    def test_preserves_frozen_kubernetes_evaluator_signature(self) -> None:
        observed: list[dict[str, object]] = []

        def evaluator(evidence: dict[str, object]) -> str:
            observed.append(evidence)
            return "kubernetes-result"

        evidence = {"state": "terminal"}
        result = _invoke_trusted_formal_evaluator(
            evaluator,
            family_id="k8s-constraint-interaction-recovery",
            evidence=evidence,
            prefix={"trace": []},
        )
        self.assertEqual(result, "kubernetes-result")
        self.assertEqual(observed, [evidence])

    def test_current_protocol_receives_prefix(self) -> None:
        def evaluator(
            evidence: dict[str, object],
            *,
            prefix: dict[str, object],
        ) -> tuple[dict[str, object], dict[str, object]]:
            return evidence, prefix

        evidence = {"state": "terminal"}
        prefix = {"trace": []}
        result = _invoke_trusted_formal_evaluator(
            evaluator,
            family_id="forgejo-release-package-publication",
            evidence=evidence,
            prefix=prefix,
        )
        self.assertEqual(result, (evidence, prefix))


class ReleaseManifestTest(unittest.TestCase):
    def _build_formal_evidence_fixture(
        self,
        root: Path,
        *,
        mutation: str | None = None,
        family_id: str = "family-1",
    ) -> dict[str, object]:
        release_id = "release-1"
        scenario_id = "scenario-1"
        domain_id = "forgejo"
        instance_id = "dev-001"
        variants = ("a", "b")
        producer_commit = "a" * 40
        evidence = root / "data" / "evidence"
        evidence.mkdir(parents=True)

        def write_json(
            name: str,
            payload: object,
        ) -> tuple[str, str]:
            path = evidence / name
            path.write_text(json.dumps(payload), encoding="utf-8")
            return (
                path.relative_to(root).as_posix(),
                file_sha256(path),
            )

        declarations: dict[str, dict[str, str]] = {}

        def emit_role(
            role: str,
            specific_payload: dict[str, object],
            support_files: list[tuple[str, str]],
        ) -> None:
            dependencies = {
                dependency: declarations[dependency]["sha256"]
                for dependency in FORMAL_EVIDENCE_DEPENDENCIES[role]
            }
            primary_payload: dict[str, object] = {
                "schema_version": "1.0",
                "artifact_type": role,
                "benchmark_release_id": release_id,
                "scenario_id": scenario_id,
                "domain_id": domain_id,
                "family_id": family_id,
                "instance_id": instance_id,
                "variant_ids": list(variants),
                "producer_commit": producer_commit,
                "input_envelope_sha256": dependencies,
                **specific_payload,
            }
            if mutation == f"empty:{role}":
                primary_payload = {"role": role}
            primary_relative, primary_sha = write_json(
                f"{role}-payload.json",
                primary_payload,
            )
            envelope_relative, _ = write_json(
                f"{role}-envelope.json",
                {
                    "schema_version": "1.0",
                    "artifact_type": role,
                    "benchmark_release_id": release_id,
                    "scenario_id": scenario_id,
                    "domain_id": domain_id,
                    "family_id": family_id,
                    "instance_id": instance_id,
                    "variant_ids": list(variants),
                    "producer_commit": producer_commit,
                    "depends_on": dependencies,
                    "primary_payload_path": primary_relative,
                    "files": [
                        {
                            "path": primary_relative,
                            "sha256": primary_sha,
                        },
                        *(
                            {
                                "path": relative,
                                "sha256": sha256,
                            }
                            for relative, sha256 in support_files
                        ),
                    ],
                },
            )
            envelope_path = root / envelope_relative
            declarations[role] = {
                "path": envelope_relative,
                "sha256": file_sha256(envelope_path),
            }

        tool_schema = write_json(
            "tool-schema.json",
            {"type": "object", "properties": {}},
        )
        tool_implementation = write_json(
            "tool-implementation.json",
            {"symbol": "invoke"},
        )
        emit_role(
            "tool_contract",
            {
                "tools": [
                    {
                        "name": "inspect_state",
                        "input_schema_path": tool_schema[0],
                        "input_schema_sha256": tool_schema[1],
                        "implementation_path": tool_implementation[0],
                        "implementation_sha256": tool_implementation[1],
                    }
                ]
            },
            [tool_schema, tool_implementation],
        )

        evaluator_implementation = write_json(
            "evaluator-implementation.json",
            {"symbol": "evaluate"},
        )
        emit_role(
            "evaluator",
            {
                "checks": [
                    {
                        "id": "goal-complete",
                        "implementation_path": evaluator_implementation[0],
                        "implementation_sha256": evaluator_implementation[1],
                    }
                ],
                "scored_state_fields": ["status"],
            },
            [evaluator_implementation],
        )

        reset_files = {
            variant: write_json(
                f"reset-{variant}.json",
                {
                    "scenario_id": scenario_id,
                    "variant_id": variant,
                    "phase": "reset",
                    "reset_verified": True,
                    "state": "clean",
                },
            )
            for variant in variants
        }
        emit_role(
            "reset_evidence",
            {
                "variants": [
                    {
                        "variant_id": variant,
                        "reset_snapshot_path": reset_files[variant][0],
                        "reset_snapshot_sha256": reset_files[variant][1],
                        "reset_verified": True,
                    }
                    for variant in variants
                ]
            },
            list(reset_files.values()),
        )

        def boundary_payload(variant: str, *, replay: bool = False) -> dict[str, object]:
            if family_id != "erpnext-manufacturing-rework":
                return {
                    "scenario_id": scenario_id,
                    "variant_id": variant,
                    "phase": "boundary",
                    "reset_snapshot_sha256": reset_files[variant][1],
                    "state": "failed",
                }
            state: dict[str, object] = {
                "corrective_job_card": {"name": "JC-1", "docstatus": 1},
                "rq_jobs": [],
            }
            if replay and mutation == "reference_terminal_rq_audit_drift":
                state["rq_jobs"] = [
                    {
                        "name": "rq-finished-1",
                        "status": "finished",
                        "arguments": '{"doc":"JC-1"}',
                    }
                ]
            semantic_state = {
                **state,
                "rq_jobs": [],
            }
            return {
                "schema_version": "1.0",
                "artifact_type": "erpnext_manufacturing_state_evidence",
                "scenario_id": scenario_id,
                "instance_id": instance_id,
                "variant_id": variant,
                "phase": "boundary",
                "reset_snapshot_sha256": reset_files[variant][1],
                "state": state,
                "state_fingerprint": canonical_state_fingerprint(state),
                "failure_state_semantic_fingerprint": (
                    canonical_state_fingerprint(semantic_state)
                ),
            }

        boundary_states = {
            variant: write_json(
                f"boundary-state-{variant}.json",
                boundary_payload(variant),
            )
            for variant in variants
        }
        failure_surfaces = {
            variant: write_json(
                f"failure-surface-{variant}.json",
                {
                    "scenario_id": scenario_id,
                    "variant_id": variant,
                    "phase": "failure_surface",
                    "operation": "submit",
                    "surface_result": "timeout",
                },
            )
            for variant in variants
        }
        emit_role(
            "boundary_bundle",
            {
                "variants": [
                    {
                        "variant_id": variant,
                        "boundary_state_path": boundary_states[variant][0],
                        "boundary_state_sha256": boundary_states[variant][1],
                        "failure_surface_path": failure_surfaces[variant][0],
                        "failure_surface_sha256": failure_surfaces[variant][1],
                        "reset_snapshot_sha256": (
                            "f" * 64
                            if mutation == "boundary_reset_mismatch"
                            and variant == "a"
                            else reset_files[variant][1]
                        ),
                        "boundary_validation_passed": True,
                    }
                    for variant in variants
                ]
            },
            [
                *boundary_states.values(),
                *failure_surfaces.values(),
            ],
        )

        reference_traces = {
            variant: write_json(
                f"reference-trace-{variant}.json",
                {
                    "scenario_id": scenario_id,
                    "variant_id": variant,
                    "phase": "reference_trace",
                    "boundary_state_sha256": boundary_states[variant][1],
                    "input_envelope_sha256": {
                        dependency: declarations[dependency]["sha256"]
                        for dependency in (
                            FORMAL_EVIDENCE_DEPENDENCIES[
                                "reference_bundle"
                            ]
                        )
                    },
                    "steps": ["repair"],
                },
            )
            for variant in variants
        }
        reference_start_states = {
            variant: write_json(
                f"reference-start-{variant}.json",
                boundary_payload(variant, replay=True),
            )
            for variant in variants
        }
        terminal_states = {
            variant: write_json(
                f"terminal-state-{variant}.json",
                {
                    "scenario_id": scenario_id,
                    "variant_id": variant,
                    "phase": "terminal",
                    "boundary_state_sha256": boundary_states[variant][1],
                    "evaluator_envelope_sha256": (
                        "d" * 64
                        if mutation == "terminal_evaluator_mismatch"
                        and variant == "a"
                        else declarations["evaluator"]["sha256"]
                    ),
                    "evaluation": {"passed": True},
                    "status": "complete",
                },
            )
            for variant in variants
        }
        emit_role(
            "reference_bundle",
            {
                "variants": [
                    {
                        "variant_id": variant,
                        "boundary_state_sha256": (
                            "e" * 64
                            if mutation == "reference_boundary_mismatch"
                            and variant == "a"
                            else boundary_states[variant][1]
                        ),
                        "reference_start_state_path": (
                            reference_start_states[variant][0]
                        ),
                        "reference_start_state_sha256": (
                            reference_start_states[variant][1]
                        ),
                        "reference_trace_path": reference_traces[variant][0],
                        "reference_trace_sha256": reference_traces[variant][1],
                        "terminal_state_path": terminal_states[variant][0],
                        "terminal_state_sha256": terminal_states[variant][1],
                        "evaluator_passed": True,
                    }
                    for variant in variants
                ]
            },
            [
                *reference_start_states.values(),
                *reference_traces.values(),
                *terminal_states.values(),
            ],
        )

        summary_report_paths = {
            variant: f"archived/control-{variant}.json"
            for variant in variants
        }
        raw_dependencies = {
            dependency: declarations[dependency]["sha256"]
            for dependency in FORMAL_EVIDENCE_DEPENDENCIES[
                "raw_run_archive"
            ]
        }
        raw_run_files = {
            variant: write_json(
                f"raw-run-{variant}.json",
                {
                    "scenario_id": (
                        "other-scenario"
                        if mutation == "raw_run_identity_mismatch"
                        and variant == "a"
                        else scenario_id
                    ),
                    "variant_id": variant,
                    "run_id": f"control-{variant}",
                    "boundary_state_sha256": boundary_states[variant][1],
                    "input_envelope_sha256": raw_dependencies,
                    "summary_report_path": (
                        "archived/wrong.json"
                        if mutation == "raw_summary_mismatch"
                        and variant == "a"
                        else summary_report_paths[variant]
                    ),
                    "execution_control": True,
                    "passed": True,
                },
            )
            for variant in variants
        }
        emit_role(
            "raw_run_archive",
            {
                "runs": [
                    {
                        "run_id": f"control-{variant}",
                        "variant_id": variant,
                        "run_path": raw_run_files[variant][0],
                        "run_sha256": raw_run_files[variant][1],
                        "summary_report_path": (
                            "archived/wrong.json"
                            if mutation == "raw_summary_mismatch"
                            and variant == "a"
                            else summary_report_paths[variant]
                        ),
                        "boundary_state_sha256": boundary_states[variant][1],
                        "execution_control": True,
                        "passed": True,
                    }
                    for variant in variants
                ]
            },
            list(raw_run_files.values()),
        )

        control_summary = write_json(
            "control-summary.json",
            {
                "completed_runs": len(variants),
                "run_errors": [],
                "task_pass_rate": 1.0,
                "execution_control_counts": {"true": len(variants)},
                "reports": [
                    {
                        "scenario_id": scenario_id,
                        "variant": variant,
                        "passed": not (
                            mutation == "control_summary_result_mismatch"
                            and variant == "a"
                        ),
                        "path": summary_report_paths[variant],
                    }
                    for variant in variants
                ],
            },
        )
        control_run_ids = [f"control-{variant}" for variant in variants]
        if mutation == "control_run_mismatch":
            control_run_ids = control_run_ids[:1]
        emit_role(
            "execution_control",
            {
                "run_ids": control_run_ids,
                "completed_runs": len(variants),
                "passed_runs": len(variants),
                "task_pass_rate": 1.0,
                "control_summary_path": control_summary[0],
                "control_summary_sha256": control_summary[1],
            },
            [control_summary],
        )
        return {
            "root": root,
            "declarations": declarations,
            "benchmark_release_id": release_id,
            "scenario_id": scenario_id,
            "domain_id": domain_id,
            "family_id": family_id,
            "instance_id": instance_id,
            "variants": variants,
            "control_evidence_path": control_summary[0],
            "control_evidence_sha256": control_summary[1],
        }

    def test_current_checkpoint_binds_four_formal_public_dev_slots(
        self,
    ) -> None:
        report = validate_release_manifest(
            load_release_manifest(default_release_manifest_path())
        )
        self.assertTrue(report.passed, report.failures)
        self.assertEqual(report.release_state, "partial_release")
        self.assertEqual(
            report.observed["hard_development_candidate_count"], 0
        )
        self.assertEqual(
            report.observed["hard_development_candidate_case_count"], 0
        )
        self.assertEqual(report.observed["formal_verified_slot_count"], 4)
        self.assertEqual(report.observed["missing_formal_slot_count"], 32)
        formal = [
            binding
            for binding in report.bindings
            if binding["quality_role"] == "release_slot"
        ]
        self.assertEqual(len(formal), 4)
        self.assertEqual(
            {binding["scenario_id"] for binding in formal},
            {
                "erpnext-sales-return-public-dev-001-r1",
                "erpnext-manufacturing-rework-public-dev-002",
                "forgejo-release-publication-public-dev-002-r1",
                "k8s-constraint-interactions-public-dev-006",
            },
        )
        self.assertTrue(
            all(binding["formal_evidence_ready"] for binding in formal)
        )
        for binding in report.bindings:
            self.assertTrue(
                binding["checks"][
                    "admission_input_artifact_sha256_match"
                ]
            )
            self.assertTrue(
                binding["checks"]["admission_report_sha256_match"]
            )
            self.assertTrue(
                binding["checks"]["admission_report_matches_recomputed"]
            )

    def test_hash_bound_but_stale_admission_report_is_rejected(self) -> None:
        source = (
            repository_root()
            / "data"
            / "scenarios"
            / "forgejo-release-publication-dev-002"
        )
        with TemporaryDirectory() as directory:
            copied = Path(directory) / source.name
            shutil.copytree(source, copied)
            scenario = load_native_scenario(copied / "scenario.json")
            admission = validate_native_scenario(scenario)
            declaration = {
                "admission_artifact_sha256": {
                    name: file_sha256(scenario.resolve_artifact(name))
                    for name in scenario.raw["admission_artifacts"]
                }
            }
            stored_path = scenario.resolve_artifact("admission")
            stored = json.loads(stored_path.read_text(encoding="utf-8"))
            stored["passed"] = not stored["passed"]
            stored_path.write_text(
                json.dumps(stored, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            declaration["admission_artifact_sha256"]["admission"] = (
                file_sha256(stored_path)
            )

            checks = _validate_admission_release_binding(
                scenario=scenario,
                admission=admission,
                declaration=declaration,
            )

            self.assertTrue(checks["admission_artifact_sha256_match"])
            self.assertTrue(checks["admission_report_sha256_match"])
            self.assertFalse(
                checks["admission_report_matches_recomputed"]
            )

    def test_manifest_bound_scenarios_have_cross_platform_lf_bytes(
        self,
    ) -> None:
        root = repository_root()
        manifest = load_release_manifest(default_release_manifest_path())
        attributes = (root / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("data/scenarios/**/*.json text eol=lf", attributes)
        self.assertIn("data/release_manifest.json text eol=lf", attributes)
        for binding in manifest["scenario_bindings"]:
            scenario = root / str(binding["scenario_path"])
            self.assertNotIn(b"\r", scenario.read_bytes())
            scenario_payload = json.loads(
                scenario.read_text(encoding="utf-8")
            )
            for relative in scenario_payload["admission_artifacts"].values():
                artifact = scenario.parent / str(relative)
                self.assertNotIn(b"\r", artifact.read_bytes())

    def test_scenario_hash_drift_invalidates_manifest(self) -> None:
        raw = copy.deepcopy(
            load_release_manifest(default_release_manifest_path())
        )
        raw["scenario_bindings"][0]["scenario_sha256"] = "0" * 64
        report = validate_release_manifest(raw)
        self.assertFalse(report.passed)
        self.assertFalse(
            report.bindings[0]["checks"]["scenario_sha256_matches"]
        )

    def test_duplicate_binding_is_rejected(self) -> None:
        raw = copy.deepcopy(
            load_release_manifest(default_release_manifest_path())
        )
        raw["scenario_bindings"].append(
            copy.deepcopy(raw["scenario_bindings"][0])
        )
        report = validate_release_manifest(raw)
        self.assertFalse(report.passed)
        self.assertFalse(report.checks["scenario_ids_unique"])
        self.assertFalse(report.checks["scenario_paths_unique"])

    def test_one_formal_slot_can_never_mean_full_release(self) -> None:
        state = derive_release_state(
            required_slot_ids={"a", "b", "c"},
            mapped_slot_ids={"a"},
            verified_slot_ids={"a"},
            release_stage="formal",
            manifest_passed=True,
        )
        self.assertEqual(state, "partial_release")

    def test_full_release_requires_exact_verified_coverage(self) -> None:
        required = {"a", "b", "c"}
        state = derive_release_state(
            required_slot_ids=required,
            mapped_slot_ids=required,
            verified_slot_ids=required,
            release_stage="formal",
            manifest_passed=True,
        )
        self.assertEqual(state, "full_release_ready")
        self.assertEqual(
            derive_release_state(
                required_slot_ids=required,
                mapped_slot_ids=required,
                verified_slot_ids=required,
                release_stage="development",
                manifest_passed=True,
            ),
            "partial_release",
        )

    def test_variant_semantics_are_not_satisfied_by_count_alone(self) -> None:
        root = repository_root()
        matrix = load_benchmark_matrix(root / "data" / "benchmark_matrix.json")
        family = benchmark_family_index(matrix)[
            ("forgejo", "forgejo-release-package-publication")
        ]
        scenario = load_native_scenario(
            root
            / "data"
            / "scenarios"
            / "forgejo-release-publication-dev-002"
            / "scenario.json"
        )
        raw = copy.deepcopy(scenario.raw)
        raw["matched_variants"][0].pop("recovery_signature_class")
        mutated = NativeScenario(path=scenario.path, raw=raw)
        checks = _validate_variant_semantics(
            scenario=mutated,
            family=family,
            boundary_taxonomy_ids={
                str(item["id"]) for item in matrix["boundary_taxonomy"]
            },
        )
        self.assertFalse(checks["variant_semantics_complete"])
        self.assertFalse(
            checks["variant_recovery_coverage_meets_profile"]
        )

    def test_control_summary_recomputes_pass_rate_and_fixes_threshold(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            summary = data / "control.json"
            summary.write_text(
                json.dumps(
                    {
                        "completed_runs": 2,
                        "run_errors": [],
                        "task_pass_rate": 0.0,
                        "execution_control_counts": {"true": 2},
                        "reports": [
                            {
                                "scenario_id": "scenario-1",
                                "variant": "a",
                                "passed": False,
                            },
                            {
                                "scenario_id": "scenario-1",
                                "variant": "b",
                                "passed": False,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            checks = _validate_control_summary(
                root=root,
                declaration={
                    "path": "data/control.json",
                    "sha256": file_sha256(summary),
                    "minimum_task_pass_rate": 0.0,
                },
                scenario_id="scenario-1",
                variants=("a", "b"),
            )
        self.assertTrue(checks["control_summary_recomputed"])
        self.assertFalse(checks["control_pass_rate_meets_threshold"])

    def test_formal_evidence_requires_role_specific_cross_bound_payloads(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            arguments = self._build_formal_evidence_fixture(root)
            self.assertTrue(validate_formal_evidence_roles(**arguments))
            declarations = arguments["declarations"]
            assert isinstance(declarations, dict)
            repeated = {
                role: dict(declarations["boundary_bundle"])
                for role in FORMAL_EVIDENCE_ROLES
            }
            self.assertFalse(
                validate_formal_evidence_roles(
                    **{**arguments, "declarations": repeated}
                )
            )

    def test_formal_evidence_rejects_empty_role_payloads(self) -> None:
        for role in FORMAL_EVIDENCE_ROLES:
            with self.subTest(role=role), TemporaryDirectory() as directory:
                arguments = self._build_formal_evidence_fixture(
                    Path(directory),
                    mutation=f"empty:{role}",
                )
                self.assertFalse(
                    validate_formal_evidence_roles(**arguments)
                )

    def test_formal_evidence_rejects_cross_role_mismatches(self) -> None:
        for mutation in (
            "boundary_reset_mismatch",
            "reference_boundary_mismatch",
            "raw_summary_mismatch",
            "control_run_mismatch",
            "raw_run_identity_mismatch",
            "terminal_evaluator_mismatch",
            "control_summary_result_mismatch",
        ):
            with (
                self.subTest(mutation=mutation),
                TemporaryDirectory() as directory,
            ):
                arguments = self._build_formal_evidence_fixture(
                    Path(directory),
                    mutation=mutation,
                )
                self.assertFalse(
                    validate_formal_evidence_roles(**arguments)
                )

    def test_formal_validator_names_the_failed_reference_contract(self) -> None:
        with TemporaryDirectory() as directory:
            arguments = self._build_formal_evidence_fixture(
                Path(directory),
                mutation="reference_boundary_mismatch",
            )
            diagnostics: list[str] = []
            self.assertFalse(
                validate_formal_evidence_roles(
                    **arguments,
                    failure_diagnostics=diagnostics,
                )
            )
            self.assertTrue(
                any(
                    value.endswith(":reference_boundary_binding")
                    for value in diagnostics
                ),
                diagnostics,
            )

    def test_manufacturing_formal_evidence_accepts_terminal_rq_audit_drift(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            arguments = self._build_formal_evidence_fixture(
                Path(directory),
                family_id="erpnext-manufacturing-rework",
                mutation="reference_terminal_rq_audit_drift",
            )
            self.assertTrue(validate_formal_evidence_roles(**arguments))

    def test_hidden_bundle_is_bound_to_active_scenario_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_root = root / "data" / "hidden-bundle"
            active_root = root / "data" / "scenarios" / "hidden-1"
            bundle_root.mkdir(parents=True)
            active_root.mkdir(parents=True)
            instance = bundle_root / "instance.json"
            instance_payload = {"scenario_id": "hidden-1", "fact": "alpha"}
            instance.write_text(
                json.dumps(instance_payload),
                encoding="utf-8",
            )
            instance_sha = hashlib.sha256(
                json.dumps(
                    instance_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            scenario_payload = {
                "scenario_id": "hidden-1",
                "instance_spec_sha256": instance_sha,
                "benchmark_split": "hidden_test",
                "benchmark_tier": "hard",
                "evaluation_status": {"hidden_test_eligible": True},
            }
            frozen_scenario = bundle_root / "scenario.json"
            active_scenario = active_root / "scenario.json"
            for path in (frozen_scenario, active_scenario):
                path.write_text(
                    json.dumps(scenario_payload),
                    encoding="utf-8",
                )
            (bundle_root / "snapshot.bin").write_bytes(b"state")
            bundle = build_frozen_bundle(
                bundle_root=bundle_root,
                scenario_path=frozen_scenario,
                instance_spec_path=instance,
                source_commit="a" * 40,
                runtime_revision="runtime-1",
                salt="fixed",
                excluded_relative_paths=(
                    "freeze.json",
                    "public.json",
                    "usage-ledger.json",
                ),
            )
            freeze = bundle_root / "freeze.json"
            public = bundle_root / "public.json"
            ledger = bundle_root / "usage-ledger.json"
            freeze.write_text(
                json.dumps(bundle.private_attestation),
                encoding="utf-8",
            )
            public.write_text(
                json.dumps(bundle.public_commitment),
                encoding="utf-8",
            )
            append_usage_event(
                ledger_path=ledger,
                event="frozen",
                details={
                    "public_commitment_sha256": bundle.public_commitment[
                        "public_commitment_sha256"
                    ]
                },
            )
            declaration = {
                "bundle_root": "data/hidden-bundle",
                "private_attestation": "data/hidden-bundle/freeze.json",
                "private_attestation_sha256": file_sha256(freeze),
                "public_commitment": "data/hidden-bundle/public.json",
                "public_commitment_file_sha256": file_sha256(public),
                "usage_ledger": "data/hidden-bundle/usage-ledger.json",
                "usage_ledger_sha256": file_sha256(ledger),
            }
            self.assertTrue(
                _validate_hidden_bundle(
                    root=root,
                    scenario_path=active_scenario,
                    declaration=declaration,
                )
            )
            scenario_payload["changed_after_freeze"] = True
            active_scenario.write_text(
                json.dumps(scenario_payload),
                encoding="utf-8",
            )
            self.assertFalse(
                _validate_hidden_bundle(
                    root=root,
                    scenario_path=active_scenario,
                    declaration=declaration,
                )
            )


if __name__ == "__main__":
    unittest.main()
