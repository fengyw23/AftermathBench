from __future__ import annotations

import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from aftermath_bench.evidence_manifest import build_file_manifest
from aftermath_bench.forgejo_formal_build_spec import (
    ForgejoFormalBuildSpecError,
    generate_forgejo_formal_build_spec,
)
from aftermath_bench.forgejo_publication_state_evidence import (
    canonical_state_fingerprint,
    deterministic_state_projection,
)
from aftermath_bench.formal_evidence_builder import (
    build_formal_inputs,
    complete_formal_evidence,
    verify_formal_input_lock,
)
from aftermath_bench.integrations.forgejo_publication_faults import (
    FORGEJO_PUBLICATION_VARIANTS,
)
from aftermath_bench.integrations.forgejo_publication_recovery import (
    evaluate_forgejo_publication_recovery,
)
from aftermath_bench.strict_json import load_json_strict

COMMIT = "a" * 40
INSTANCE_SHA = "b" * 64
SCENARIO_ID = "forgejo-publication-public-dev-test"
RELEASE_ID = "formal-test-r1"
OUTPUT = f"data/formal/{RELEASE_ID}/{SCENARIO_ID}"
SURFACE = "HTTP connection lost before publication completion was acknowledged"


class _Fixture:
    @staticmethod
    def _prefix_payload() -> dict:
        return {
            "scenario_id": SCENARIO_ID,
            "instance_spec_sha256": INSTANCE_SHA,
            "pull_request_index": 2,
            "linked_issue_index": 1,
            "milestone_id": 1,
            "protected_pull_request_index": 3,
            "protected_issue_index": 4,
            "coordinator_hook_id": 7,
            "provenance_hook_id": 8,
            "base_branch": "release/2026.08",
            "branch_protection_rule": "release/*",
            "release_tag": "v2026.08.0",
            "protected_release_tag": "v2026.07.3",
            "protected_asset_name": "prior.sha256",
            "expected_assets": [
                {"name": "binary.tgz", "sha256": "hash-a"},
                {"name": "binary.tgz.sha256", "sha256": "hash-b"},
                {"name": "binary.spdx.json", "sha256": "hash-c"},
            ],
            "trace": [],
        }

    @staticmethod
    def _final_evidence() -> dict:
        return {
            "target_pull": {
                "state": "closed",
                "merged": True,
                "merge_base": "abc123",
            },
            "linked_issue": {"state": "closed"},
            "release_milestone": {"state": "closed"},
            "base_branch": {"commit": {"id": "abc123"}},
            "releases": [
                {
                    "id": 20,
                    "tag_name": "v2026.08.0",
                    "target_commitish": "release/2026.08",
                },
                {
                    "id": 19,
                    "tag_name": "v2026.07.3",
                    "target_commitish": "main",
                },
            ],
            "target_release_assets": [
                {"name": "binary.tgz", "content_sha256": "hash-a"},
                {
                    "name": "binary.tgz.sha256",
                    "content_sha256": "hash-b",
                },
                {
                    "name": "binary.spdx.json",
                    "content_sha256": "hash-c",
                },
            ],
            "protected_release_assets": [{"name": "prior.sha256"}],
            "protected_pull": {"state": "open", "merged": False},
            "protected_issue": {"state": "open"},
            "branch_protections": [{"rule_name": "release/*"}],
            "hooks": [
                {"id": 7, "active": True},
                {"id": 8, "active": True},
            ],
            "coordinator_history": [{"uuid": "delivery-a", "status": "succeeded"}],
            "provenance_history": [{"uuid": "delivery-b", "status": "succeeded"}],
            "external_deliveries": [
                {
                    "key": "delivery-a",
                    "attempt_count": 1,
                    "payload": {"release": {"tag_name": "v2026.08.0"}},
                },
                {
                    "key": "delivery-b",
                    "attempt_count": 1,
                    "payload": {"release": {"tag_name": "v2026.08.0"}},
                },
            ],
        }

    def __init__(self, root: Path) -> None:
        self.root = root
        self.scenario_directory = root / "data" / "scenarios" / SCENARIO_ID
        self.artifacts = self.scenario_directory / "artifacts"
        self.runtime_bundle = root / "data" / "evidence" / "native"
        self.control_bundle = root / "data" / "evidence" / "control"
        self.capture_directory = self.runtime_bundle / "runtime" / "state-evidence"
        self.bundle_directory = root / "data" / "bundles"
        self.scenario_path = self.scenario_directory / "scenario.json"
        self.runtime_manifest = self.runtime_bundle / "files.json"
        self.control_manifest = self.control_bundle / "files.json"
        self.capture_bundle_manifests: list[Path] = []
        self._write_sources()
        self._write_scenario()
        self._write_capture_bundles()
        self._write_runtime_and_captures()
        self._write_exact_manifest(
            self.runtime_bundle,
            self.runtime_manifest,
        )

    @staticmethod
    def _bytes(value: object) -> bytes:
        return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    def write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self._bytes(value))

    def _write_sources(self) -> None:
        paths = (
            "src/aftermath_bench/native_forgejo_publication_family.py",
            "src/aftermath_bench/integrations/forgejo_publication_recovery.py",
            "src/aftermath_bench/integrations/forgejo_api.py",
            "src/aftermath_bench/integrations/forgejo_web.py",
            "runtimes/forgejo/compose.yaml",
            "runtimes/forgejo/control/Containerfile",
            "src/aftermath_bench/runtime_services/__init__.py",
            "src/aftermath_bench/runtime_services/gateway.py",
            "src/aftermath_bench/runtime_services/webhook_sink.py",
            "scripts/build_forgejo_runtime.py",
            "scripts/manage_forgejo_stack.py",
            "scripts/run_forgejo_publication_boundary.py",
            "scripts/capture_forgejo_publication_state_evidence.py",
            "src/aftermath_bench/integrations/forgejo_publication_faults.py",
        )
        for relative in paths:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# fixture source: {relative}\n", encoding="utf-8")
        image = "fixture/forgejo:verified"
        base_reference = "fixture/base:1"
        base_digest = f"sha256:{'e' * 64}"
        self.write_json(
            self.root / "runtimes" / "forgejo" / "runtime.lock.json",
            {
                "schema_version": "0.1",
                "image": image,
                "source": {
                    "repository": "https://example.invalid/forgejo",
                    "revision": COMMIT,
                    "license": "GPL-3.0-or-later",
                    "containerfile": "Dockerfile",
                },
                "base_images": {
                    "base": {
                        "reference": base_reference,
                        "digest": base_digest,
                    }
                },
                "base_image_digest_status": "resolved",
                "execution_status": ("source_checkout_with_pinned_build_plan"),
            },
        )
        source_sha256 = "d" * 64
        self.write_json(
            self.runtime_bundle / "runtime" / "source-verification.json",
            {
                "plan": {
                    "revision": COMMIT,
                    "image": image,
                    "expected_hashes": [
                        {
                            "path": "Dockerfile",
                            "sha256": source_sha256,
                        }
                    ],
                    "base_images": [
                        {
                            "reference": base_reference,
                            "digest": base_digest,
                        }
                    ],
                },
                "source_verification": {
                    "revision": COMMIT,
                    "expected_revision": COMMIT,
                    "passed": True,
                    "checks": {
                        "revision": True,
                        "sha256:Dockerfile": True,
                    },
                    "actual_hashes": {
                        "Dockerfile": source_sha256,
                    },
                    "pinned_containerfile": {
                        "all_digests_pinned": True,
                        "semantic_version_pinned": True,
                    },
                },
                "image_build": {
                    "image": image,
                    "built_from_verified_revision": COMMIT,
                },
            },
        )

    def _write_scenario(self) -> None:
        for name in (
            "reference",
            "observed_graph",
            "baselines",
            "admission",
        ):
            self.write_json(
                self.artifacts / f"{name}.json",
                {"scenario_id": SCENARIO_ID},
            )
        self.write_json(
            self.artifacts / "prefix.json",
            self._prefix_payload(),
        )
        self.write_json(
            self.scenario_path,
            {
                "schema_version": "1.0",
                "scenario_id": SCENARIO_ID,
                "domain_id": "forgejo",
                "instance_id": "dev-002",
                "instance_spec_sha256": INSTANCE_SHA,
                "family": "forgejo-release-package-publication",
                "runtime_id": "forgejo-main",
                "benchmark_split": "public_dev",
                "benchmark_tier": "hard",
                "admission_status": "validated_hard",
                "title": "Formal fixture",
                "user_instruction": "Complete publication safely.",
                "ambiguous_operation": {
                    "operation": "finalize approved release bundle",
                    "surface_result": SURFACE,
                },
                "matched_variants": [
                    {"id": variant} for variant in FORGEJO_PUBLICATION_VARIANTS
                ],
                "admission_artifacts": {
                    "admission": "artifacts/admission.json",
                    "prefix": "artifacts/prefix.json",
                    "reference": "artifacts/reference.json",
                    "observed_graph": "artifacts/observed_graph.json",
                    "baselines": "artifacts/baselines.json",
                },
            },
        )

    def _write_capture_bundles(self) -> None:
        for phase, byte in (("reset", "1"), ("boundary", "2")):
            path = self.bundle_directory / phase / "bundle.json"
            self.write_json(
                path,
                {
                    "schema_version": "1.0",
                    "capture_mode": "simultaneous_service_quiescence",
                    "forgejo_sha256": byte * 64,
                    "webhook_sink_sha256": byte.upper() * 64,
                },
            )
            self.capture_bundle_manifests.append(path)

    @staticmethod
    def _bundle_binding(path: Path, size: int) -> dict:
        manifest = load_json_strict(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "manifest": manifest,
            "manifest_file_sha256": digest,
            "forgejo_archive": {
                "sha256": manifest["forgejo_sha256"],
                "size_bytes": size,
            },
            "webhook_sink_archive": {
                "sha256": manifest["webhook_sink_sha256"],
                "size_bytes": size + 1,
            },
        }

    def _raw_boundary(self, variant: str) -> dict:
        return {
            "schema_version": "1.0",
            "scenario_id": SCENARIO_ID,
            "instance_spec_sha256": INSTANCE_SHA,
            "variant": variant,
            "surface_result": SURFACE,
            "visible_failure": self._visible_failure(),
            "checks": {"surface_error_observed": True},
            "passed": True,
        }

    @staticmethod
    def _visible_failure() -> dict:
        return {
            "ok": False,
            "error": SURFACE,
            "receiver_evidence": {
                "body_sha256": "a" * 64,
            },
        }

    @classmethod
    def _evaluation(cls, evidence: dict | None = None) -> dict:
        result = evaluate_forgejo_publication_recovery(
            evidence or cls._final_evidence(),
            prefix=cls._prefix_payload(),
        )
        return {
            "passed": result.passed,
            "components": result.components,
            "checks": result.checks,
            "diagnostics": result.diagnostics,
            "failures": list(result.failures),
        }

    def _write_runtime_and_captures(self) -> None:
        prefix_hash = hashlib.sha256(
            (self.artifacts / "prefix.json").read_bytes()
        ).hexdigest()
        reset_bundle = self._bundle_binding(
            self.capture_bundle_manifests[0],
            101,
        )
        boundary_bundle = self._bundle_binding(
            self.capture_bundle_manifests[1],
            201,
        )
        for variant in FORGEJO_PUBLICATION_VARIANTS:
            raw_boundary = self._raw_boundary(variant)
            raw_boundary_path = (
                self.runtime_bundle / "runtime" / f"{variant}-boundary.json"
            )
            self.write_json(raw_boundary_path, raw_boundary)
            self.write_json(
                self.runtime_bundle / "runtime" / f"{variant}-reference.json",
                {
                    "schema_version": "1.0",
                    "scenario_id": SCENARIO_ID,
                    "instance_spec_sha256": INSTANCE_SHA,
                    "variant": variant,
                    "control": "deterministic-reference",
                    "reference_trace": [
                        {
                            "tool": "list_releases",
                            "arguments": {},
                            "result": {
                                "ok": True,
                                "result": [
                                    {
                                        "body_sha256": "b" * 64,
                                    }
                                ],
                            },
                        }
                    ],
                    "control_error": None,
                    "final_evidence": self._final_evidence(),
                    "evaluation": self._evaluation(),
                },
            )
            reset_state = {"variant": variant, "state": "reset"}
            reset = {
                "schema_version": "1.0",
                "artifact_type": ("forgejo_publication_native_state_projection"),
                "scenario_id": SCENARIO_ID,
                "instance_spec_sha256": INSTANCE_SHA,
                "prefix_file_sha256": prefix_hash,
                "variant_id": variant,
                "phase": "reset",
                "bundle_manifest_file_sha256": reset_bundle["manifest_file_sha256"],
                "bundle": reset_bundle,
                "state_projection": reset_state,
                "state_fingerprint": canonical_state_fingerprint(
                    deterministic_state_projection(reset_state)
                ),
                "expected_projection": {
                    "provided": True,
                    "file_sha256": "3" * 64,
                    "state_fingerprint": canonical_state_fingerprint(
                        deterministic_state_projection(reset_state)
                    ),
                    "exact_match": True,
                },
                "reset_verified": True,
            }
            reset_path = self.capture_directory / f"{variant}-reset.json"
            self.write_json(reset_path, reset)
            boundary_state = {"variant": variant, "state": "boundary"}
            boundary_capture_path = self.capture_directory / f"{variant}-boundary.json"
            self.write_json(
                boundary_capture_path,
                {
                    "schema_version": "1.0",
                    "artifact_type": ("forgejo_publication_native_state_projection"),
                    "scenario_id": SCENARIO_ID,
                    "instance_spec_sha256": INSTANCE_SHA,
                    "prefix_file_sha256": prefix_hash,
                    "variant_id": variant,
                    "phase": "boundary",
                    "reset_snapshot_sha256": hashlib.sha256(
                        reset_path.read_bytes()
                    ).hexdigest(),
                    "failure_report_file_sha256": hashlib.sha256(
                        raw_boundary_path.read_bytes()
                    ).hexdigest(),
                    "surface_result": SURFACE,
                    "visible_failure": self._visible_failure(),
                    "harness_error_type": "RemoteDisconnected",
                    "bundle_manifest_file_sha256": boundary_bundle[
                        "manifest_file_sha256"
                    ],
                    "bundle": boundary_bundle,
                    "state_projection": boundary_state,
                    "state_fingerprint": canonical_state_fingerprint(
                        deterministic_state_projection(boundary_state)
                    ),
                    "boundary_validation_passed": True,
                },
            )
            reference_start_path = (
                self.capture_directory / f"{variant}-reference-start.json"
            )
            reference_start_path.write_bytes(boundary_capture_path.read_bytes())

    def _write_exact_manifest(
        self,
        directory: Path,
        manifest_path: Path,
    ) -> None:
        self.write_json(
            manifest_path,
            build_file_manifest(directory, exclude={"files.json"}),
        )

    def write_controls(
        self,
        *,
        failed_variants: tuple[str, ...] = (),
    ) -> None:
        reports = []
        for variant in FORGEJO_PUBLICATION_VARIANTS:
            passed = variant not in failed_variants
            pre_model_boundary_path = (
                self.control_bundle
                / "pre-model-boundaries"
                / f"{variant}-boundary.json"
            )
            pre_model_boundary_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            pre_model_boundary_path.write_bytes(
                (self.capture_directory / f"{variant}-boundary.json").read_bytes()
            )
            pre_model_boundary_sha256 = hashlib.sha256(
                pre_model_boundary_path.read_bytes()
            ).hexdigest()
            path = (
                self.control_bundle / "model-runs" / "repetition-01" / f"{variant}.json"
            )
            lock = verify_formal_input_lock(
                self.root / OUTPUT / "formal-input-lock.json",
                root=self.root,
                scenario_id=SCENARIO_ID,
                domain_id="forgejo",
                family_id="forgejo-release-package-publication",
                instance_id="dev-002",
                variant_id=variant,
                failure_report_path=(
                    self.runtime_bundle / "runtime" / f"{variant}-boundary.json"
                ),
                prefix_path=self.artifacts / "prefix.json",
                trusted_producer_commit=COMMIT,
            ).as_dict()
            final_evidence = self._final_evidence()
            if not passed:
                final_evidence["releases"] = [
                    release
                    for release in final_evidence["releases"]
                    if release["tag_name"] != "v2026.08.0"
                ]
            evaluation = self._evaluation(final_evidence)
            self.write_json(
                path,
                {
                    "schema_version": "1.0",
                    "run_id": f"control-{variant}",
                    "scenario_id": SCENARIO_ID,
                    "instance_id": "dev-002",
                    "instance_spec_sha256": INSTANCE_SHA,
                    "family": "forgejo-release-package-publication",
                    "domain": "forgejo",
                    "variant": variant,
                    "execution_control": True,
                    "stop_reason": "model_stopped",
                    "surface_failure": self._visible_failure(),
                    "turns": [{"turn": 1, "tool_calls": []}],
                    "final_evidence": final_evidence,
                    "evaluation": evaluation,
                    "formal_input_lock": lock,
                    "pre_model_boundary_evidence": {
                        "variant_id": variant,
                        "source_basename": (pre_model_boundary_path.name),
                        "sha256": pre_model_boundary_sha256,
                    },
                },
            )
            reports.append(
                {
                    "scenario_id": SCENARIO_ID,
                    "variant": variant,
                    "passed": passed,
                    "path": (f"/runner/model-runs/repetition-01/{variant}.json"),
                }
            )
        self.write_json(
            self.control_bundle / "model-runs" / "summary.json",
            {
                "schema_version": "1.0",
                "completed_runs": 8,
                "run_errors": [],
                "task_pass_rate": ((8 - len(failed_variants)) / 8),
                "execution_control_counts": {"true": 8},
                "reports": reports,
            },
        )
        self._write_exact_manifest(
            self.control_bundle,
            self.control_manifest,
        )


def _admission_report() -> SimpleNamespace:
    return SimpleNamespace(
        passed=True,
        admitted_tier="hard",
        scenario_id=SCENARIO_ID,
    )


class ForgejoFormalBuildSpecTest(unittest.TestCase):
    def _generate_inputs(self, fixture: _Fixture):
        with (
            patch(
                "aftermath_bench.forgejo_formal_build_spec.validate_native_scenario",
                return_value=_admission_report(),
            ),
            patch(
                "aftermath_bench.forgejo_formal_build_spec._current_git_commit",
                return_value=COMMIT,
            ),
        ):
            return generate_forgejo_formal_build_spec(
                root=fixture.root,
                benchmark_release_id=RELEASE_ID,
                output_directory=OUTPUT,
                runtime_manifest_path=fixture.runtime_manifest,
                capture_directory=fixture.capture_directory,
                capture_bundle_manifest_paths=(fixture.capture_bundle_manifests),
                phase="inputs",
                scenario_path=fixture.scenario_path,
            )

    def _generate_complete(
        self,
        fixture: _Fixture,
        *,
        lock_path: Path,
    ):
        with (
            patch(
                "aftermath_bench.forgejo_formal_build_spec.validate_native_scenario",
                return_value=_admission_report(),
            ),
            patch(
                "aftermath_bench.forgejo_formal_build_spec._current_git_commit",
                return_value=COMMIT,
            ),
        ):
            return generate_forgejo_formal_build_spec(
                root=fixture.root,
                benchmark_release_id=RELEASE_ID,
                output_directory=OUTPUT,
                runtime_manifest_path=fixture.runtime_manifest,
                capture_directory=fixture.capture_directory,
                capture_bundle_manifest_paths=(fixture.capture_bundle_manifests),
                phase="complete",
                scenario_path=fixture.scenario_path,
                control_manifest_path=fixture.control_manifest,
                model_input_lock_path=lock_path,
            )

    def test_inputs_spec_binds_all_tools_checks_and_native_variants(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            result = self._generate_inputs(fixture)
            spec = result.spec

            self.assertEqual(len(spec["variant_ids"]), 8)
            tools = spec["roles"]["tool_contract"]["primary_payload"]["tools"]
            self.assertEqual(len(tools), 17)
            self.assertEqual(len({tool["name"] for tool in tools}), 17)
            self.assertEqual(
                len(spec["roles"]["evaluator"]["primary_payload"]["checks"]),
                len(fixture._evaluation()["checks"]),
            )
            boundary = spec["roles"]["boundary_bundle"]["primary_payload"]["variants"]
            self.assertTrue(
                all(
                    "raw_failure_report_path" in item
                    and "raw_failure_report_sha256" in item
                    for item in boundary
                )
            )
            for role in (
                "tool_contract",
                "evaluator",
                "reset_evidence",
                "boundary_bundle",
                "reference_bundle",
            ):
                for support in spec["roles"][role]["support_files"]:
                    self.assertIn(
                        f"{OUTPUT}/roles/{role}/support/",
                        support["path"],
                    )
            self.assertEqual(
                spec["roles"]["raw_run_archive"]["support_files"],
                [],
            )

    def test_two_phase_spec_builds_an_authoritatively_valid_package(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            inputs = self._generate_inputs(fixture)
            lock = build_formal_inputs(
                inputs.spec,
                root=fixture.root,
                trusted_producer_commit=COMMIT,
            )
            fixture.write_controls()
            complete = self._generate_complete(
                fixture,
                lock_path=fixture.root / lock.input_lock_path,
            )
            result = complete_formal_evidence(
                complete.spec,
                root=fixture.root,
                trusted_producer_commit=COMMIT,
            )

            self.assertEqual(
                result.declarations_manifest_path,
                f"{OUTPUT}/completion/declarations.json",
            )
            raw = complete.spec["roles"]["raw_run_archive"]
            self.assertEqual(len(raw["primary_payload"]["runs"]), 8)
            self.assertTrue(
                all(
                    item["formal_input_lock_sha256"]
                    == {"$formal_input_lock_sha256": True}
                    for item in raw["primary_payload"]["runs"]
                )
            )
            summary = complete.spec["roles"]["execution_control"]["support_files"][0][
                "json_content"
            ]
            self.assertTrue(
                all(
                    report["path"].startswith(
                        f"{OUTPUT}/completion/roles/"
                        "raw_run_archive/support/trajectories/"
                    )
                    for report in summary["reports"]
                )
            )

    def test_complete_rejects_missing_or_drifted_trajectory_lock(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            inputs = self._generate_inputs(fixture)
            lock = build_formal_inputs(
                inputs.spec,
                root=fixture.root,
                trusted_producer_commit=COMMIT,
            )
            lock_path = fixture.root / lock.input_lock_path
            fixture.write_controls()
            trajectory_path = (
                fixture.control_bundle
                / "model-runs"
                / "repetition-01"
                / f"{FORGEJO_PUBLICATION_VARIANTS[0]}.json"
            )
            trajectory = load_json_strict(trajectory_path)
            recorded_lock = deepcopy(trajectory["formal_input_lock"])
            trajectory.pop("formal_input_lock")
            fixture.write_json(trajectory_path, trajectory)
            fixture._write_exact_manifest(
                fixture.control_bundle,
                fixture.control_manifest,
            )
            with self.assertRaisesRegex(
                ForgejoFormalBuildSpecError,
                "lacks its verified formal input lock",
            ):
                self._generate_complete(
                    fixture,
                    lock_path=lock_path,
                )

            recorded_lock["boundary_state_sha256"] = "f" * 64
            trajectory["formal_input_lock"] = recorded_lock
            fixture.write_json(trajectory_path, trajectory)
            fixture._write_exact_manifest(
                fixture.control_bundle,
                fixture.control_manifest,
            )
            with self.assertRaisesRegex(
                ForgejoFormalBuildSpecError,
                "does not exactly match",
            ):
                self._generate_complete(
                    fixture,
                    lock_path=lock_path,
                )

    def test_seven_of_eight_controls_are_accepted_but_six_are_not(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            inputs = self._generate_inputs(fixture)
            lock = build_formal_inputs(
                inputs.spec,
                root=fixture.root,
                trusted_producer_commit=COMMIT,
            )
            lock_path = fixture.root / lock.input_lock_path
            fixture.write_controls(
                failed_variants=(FORGEJO_PUBLICATION_VARIANTS[0],),
            )
            complete = self._generate_complete(
                fixture,
                lock_path=lock_path,
            )
            control = complete.spec["roles"]["execution_control"]["primary_payload"]
            self.assertEqual(control["passed_runs"], 7)
            self.assertEqual(control["task_pass_rate"], 0.875)
            result = complete_formal_evidence(
                complete.spec,
                root=fixture.root,
                trusted_producer_commit=COMMIT,
            )
            self.assertEqual(result.control_evidence["minimum_task_pass_rate"], 0.8)

            fixture.write_controls(
                failed_variants=FORGEJO_PUBLICATION_VARIANTS[:2],
            )
            with self.assertRaisesRegex(
                ForgejoFormalBuildSpecError,
                "below or inconsistent",
            ):
                self._generate_complete(
                    fixture,
                    lock_path=lock_path,
                )

    def test_rejects_manifest_drift_and_nonpassing_reference(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            boundary = (
                fixture.runtime_bundle
                / "runtime"
                / f"{FORGEJO_PUBLICATION_VARIANTS[0]}-boundary.json"
            )
            boundary.write_bytes(boundary.read_bytes() + b" ")
            with (
                patch(
                    "aftermath_bench.forgejo_formal_build_spec."
                    "validate_native_scenario",
                    return_value=_admission_report(),
                ),
                patch(
                    "aftermath_bench.forgejo_formal_build_spec._current_git_commit",
                    return_value=COMMIT,
                ),
                self.assertRaisesRegex(
                    ForgejoFormalBuildSpecError,
                    "bytes drifted",
                ),
            ):
                self._generate_inputs(fixture)

        with TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            reference = (
                fixture.runtime_bundle
                / "runtime"
                / f"{FORGEJO_PUBLICATION_VARIANTS[0]}-reference.json"
            )
            payload = load_json_strict(reference)
            payload["evaluation"]["passed"] = False
            self._rewrite_bundle_file(fixture, reference, payload)
            with self.assertRaisesRegex(
                ForgejoFormalBuildSpecError,
                "complete passing deterministic recovery",
            ):
                self._generate_inputs(fixture)

    @staticmethod
    def _rewrite_bundle_file(
        fixture: _Fixture,
        path: Path,
        value: object,
    ) -> None:
        fixture.write_json(path, value)
        fixture.write_json(
            fixture.runtime_manifest,
            build_file_manifest(
                fixture.runtime_bundle,
                exclude={"files.json"},
            ),
        )

    def test_requires_complete_phase_lock_and_control(self) -> None:
        with TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            with (
                self.assertRaisesRegex(
                    ForgejoFormalBuildSpecError,
                    "requires control manifest and input lock",
                ),
                patch(
                    "aftermath_bench.forgejo_formal_build_spec."
                    "validate_native_scenario",
                    return_value=_admission_report(),
                ),
                patch(
                    "aftermath_bench.forgejo_formal_build_spec._current_git_commit",
                    return_value=COMMIT,
                ),
            ):
                generate_forgejo_formal_build_spec(
                    root=fixture.root,
                    benchmark_release_id=RELEASE_ID,
                    output_directory=OUTPUT,
                    runtime_manifest_path=fixture.runtime_manifest,
                    capture_directory=fixture.capture_directory,
                    capture_bundle_manifest_paths=(fixture.capture_bundle_manifests),
                    phase="complete",
                    scenario_path=fixture.scenario_path,
                )


if __name__ == "__main__":
    unittest.main()
