from __future__ import annotations

import copy
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from aftermath_bench.formal_evidence_builder import (
    FormalEvidenceBuildError,
    build_formal_evidence,
    build_formal_inputs,
    complete_formal_evidence,
    load_formal_evidence_build_spec,
    verify_formal_input_lock,
)
from aftermath_bench.release_manifest import (
    TRUSTED_FORMAL_EVALUATORS,
    file_sha256,
    validate_formal_evidence_roles,
)
from aftermath_bench.strict_json import load_json_strict


class FormalEvidenceBuilderTest(unittest.TestCase):
    commit = "a" * 40
    variants = ("a", "b")

    @staticmethod
    def _test_evaluator(
        evidence: dict[str, object],
        *,
        prefix: dict[str, object],
    ) -> SimpleNamespace:
        del prefix
        passed = evidence.get("status") == "complete"
        return SimpleNamespace(
            passed=passed,
            components={"goal": passed},
            checks={"goal-complete": passed},
            diagnostics={},
            failures=() if passed else ("goal-complete",),
        )

    def setUp(self) -> None:
        evaluator_patch = patch.dict(
            TRUSTED_FORMAL_EVALUATORS,
            {"family-1": self._test_evaluator},
        )
        evaluator_patch.start()
        self.addCleanup(evaluator_patch.stop)

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _snapshot(self, root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): file_sha256(path)
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def _scenario(self, root: Path, *, split: str = "public_dev") -> str:
        relative = "data/scenarios/scenario-1/scenario.json"
        scenario_path = root / relative
        artifacts = scenario_path.parent / "artifacts"
        artifacts.mkdir(parents=True)
        for name in ("prefix.json", "reference.json", "graph.json", "baselines.json"):
            self._write_json(artifacts / name, {"artifact": name})
        self._write_json(
            scenario_path,
            {
                "schema_version": "1.0",
                "scenario_id": "scenario-1",
                "domain_id": "forgejo",
                "instance_id": "dev-001",
                "family": "family-1",
                "runtime_id": "forgejo-main",
                "benchmark_split": split,
                "benchmark_tier": "hard",
                "title": "Formal evidence builder integration scenario",
                "user_instruction": "Recover the failed publication.",
                "ambiguous_operation": {
                    "operation": "publish",
                    "surface_result": "connection lost",
                },
                "matched_variants": [
                    {"id": variant} for variant in self.variants
                ],
                "admission_artifacts": {
                    "prefix": "artifacts/prefix.json",
                    "reference": "artifacts/reference.json",
                    "observed_graph": "artifacts/graph.json",
                    "baselines": "artifacts/baselines.json",
                },
            },
        )
        return relative

    def _spec(
        self,
        root: Path,
        *,
        split: str = "public_dev",
    ) -> dict[str, object]:
        scenario_path = self._scenario(root, split=split)
        source_dir = root / "data" / "build-sources"
        self._write_json(source_dir / "tool.json", {"symbol": "inspect"})
        self._write_json(
            source_dir / "evaluator.json",
            {"symbol": "evaluate"},
        )
        output = "data/formal/release-1/scenario-1"

        def support(role: str, name: str) -> str:
            phase = (
                ""
                if role
                in {
                    "tool_contract",
                    "evaluator",
                    "reset_evidence",
                    "boundary_bundle",
                    "reference_bundle",
                }
                else "/completion"
            )
            return f"{output}{phase}/roles/{role}/support/{name}"

        def file_hash(path: str) -> dict[str, str]:
            return {"$file_sha256": path}

        def envelope_hash(role: str) -> dict[str, str]:
            return {"$envelope_sha256": role}

        def dependencies(role: str) -> dict[str, str]:
            return {"$role_dependencies": role}

        def identity(field: str) -> dict[str, str]:
            return {"$identity": field}

        tool_schema = support("tool_contract", "input-schema.json")
        tool_implementation = support(
            "tool_contract",
            "implementation.json",
        )
        evaluator_implementation = support(
            "evaluator",
            "implementation.json",
        )
        reset_paths = {
            variant: support("reset_evidence", f"reset-{variant}.json")
            for variant in self.variants
        }
        prefix_path = support(
            "reset_evidence",
            "common-prefix.json",
        )
        boundary_paths = {
            variant: support(
                "boundary_bundle",
                f"boundary-{variant}.json",
            )
            for variant in self.variants
        }
        failure_paths = {
            variant: support(
                "boundary_bundle",
                f"failure-{variant}.json",
            )
            for variant in self.variants
        }
        raw_failure_paths = {
            variant: support(
                "boundary_bundle",
                f"raw-failure-{variant}.json",
            )
            for variant in self.variants
        }
        trace_paths = {
            variant: support(
                "reference_bundle",
                f"trace-{variant}.json",
            )
            for variant in self.variants
        }
        reference_start_paths = {
            variant: support(
                "reference_bundle",
                f"start-{variant}.json",
            )
            for variant in self.variants
        }
        terminal_paths = {
            variant: support(
                "reference_bundle",
                f"terminal-{variant}.json",
            )
            for variant in self.variants
        }
        raw_paths = {
            variant: support(
                "raw_run_archive",
                f"run-{variant}.json",
            )
            for variant in self.variants
        }
        trajectory_paths = {
            variant: support(
                "raw_run_archive",
                f"trajectory-{variant}.json",
            )
            for variant in self.variants
        }
        pre_model_paths = {
            variant: support(
                "raw_run_archive",
                f"pre-model-{variant}.json",
            )
            for variant in self.variants
        }
        summary_path = support(
            "execution_control",
            "control-summary.json",
        )
        report_paths = {
            variant: trajectory_paths[variant]
            for variant in self.variants
        }

        roles: dict[str, object] = {
            "tool_contract": {
                "primary_payload": {
                    "tools": [
                        {
                            "name": "inspect-state",
                            "input_schema_path": tool_schema,
                            "input_schema_sha256": file_hash(tool_schema),
                            "implementation_path": tool_implementation,
                            "implementation_sha256": file_hash(
                                tool_implementation
                            ),
                        }
                    ]
                },
                "support_files": [
                    {
                        "path": tool_schema,
                        "json_content": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                    {
                        "path": tool_implementation,
                        "source_path": "data/build-sources/tool.json",
                    },
                ],
            },
            "evaluator": {
                "primary_payload": {
                    "checks": [
                        {
                            "id": "goal-complete",
                            "implementation_path": (
                                evaluator_implementation
                            ),
                            "implementation_sha256": file_hash(
                                evaluator_implementation
                            ),
                        }
                    ],
                    "scored_state_fields": ["status"],
                },
                "support_files": [
                    {
                        "path": evaluator_implementation,
                        "source_path": (
                            "data/build-sources/evaluator.json"
                        ),
                    }
                ],
            },
            "reset_evidence": {
                "primary_payload": {
                    "prefix_path": prefix_path,
                    "prefix_sha256": file_hash(prefix_path),
                    "variants": [
                        {
                            "variant_id": variant,
                            "reset_snapshot_path": reset_paths[variant],
                            "reset_snapshot_sha256": file_hash(
                                reset_paths[variant]
                            ),
                            "reset_verified": True,
                        }
                        for variant in self.variants
                    ]
                },
                "support_files": [
                    {
                        "path": prefix_path,
                        "source_path": (
                            "data/scenarios/scenario-1/"
                            "artifacts/prefix.json"
                        ),
                    },
                    *[
                        {
                            "path": reset_paths[variant],
                            "json_content": {
                                "scenario_id": identity("scenario_id"),
                                "variant_id": variant,
                                "phase": "reset",
                                "reset_verified": True,
                                "prefix_file_sha256": file_hash(
                                    prefix_path
                                ),
                                "state": "clean",
                            },
                        }
                        for variant in self.variants
                    ],
                ],
            },
            "boundary_bundle": {
                "primary_payload": {
                    "variants": [
                        {
                            "variant_id": variant,
                            "boundary_state_path": boundary_paths[variant],
                            "boundary_state_sha256": file_hash(
                                boundary_paths[variant]
                            ),
                            "failure_surface_path": failure_paths[variant],
                            "failure_surface_sha256": file_hash(
                                failure_paths[variant]
                            ),
                            "raw_failure_report_path": (
                                raw_failure_paths[variant]
                            ),
                            "raw_failure_report_sha256": file_hash(
                                raw_failure_paths[variant]
                            ),
                            "reset_snapshot_sha256": file_hash(
                                reset_paths[variant]
                            ),
                            "boundary_validation_passed": True,
                        }
                        for variant in self.variants
                    ]
                },
                "support_files": [
                    *[
                        {
                            "path": boundary_paths[variant],
                            "json_content": {
                                "scenario_id": identity("scenario_id"),
                                "variant_id": variant,
                                "phase": "boundary",
                                "reset_snapshot_sha256": file_hash(
                                    reset_paths[variant]
                                ),
                                "state": "failed",
                            },
                        }
                        for variant in self.variants
                    ],
                    *[
                        {
                            "path": failure_paths[variant],
                            "json_content": {
                                "scenario_id": identity("scenario_id"),
                                "variant_id": variant,
                                "phase": "failure_surface",
                                "operation": "submit",
                                "surface_result": "timeout",
                            },
                        }
                        for variant in self.variants
                    ],
                    *[
                        {
                            "path": raw_failure_paths[variant],
                            "json_content": {
                                "native_report": "connection lost",
                                "variant_id": variant,
                                "request_id": f"request-{variant}",
                            },
                        }
                        for variant in self.variants
                    ],
                ],
            },
            "reference_bundle": {
                "primary_payload": {
                    "variants": [
                        {
                            "variant_id": variant,
                            "boundary_state_sha256": file_hash(
                                boundary_paths[variant]
                            ),
                            "reference_start_state_path": (
                                reference_start_paths[variant]
                            ),
                            "reference_start_state_sha256": file_hash(
                                reference_start_paths[variant]
                            ),
                            "reference_trace_path": trace_paths[variant],
                            "reference_trace_sha256": file_hash(
                                trace_paths[variant]
                            ),
                            "terminal_state_path": terminal_paths[variant],
                            "terminal_state_sha256": file_hash(
                                terminal_paths[variant]
                            ),
                            "evaluator_passed": True,
                        }
                        for variant in self.variants
                    ]
                },
                "support_files": [
                    *[
                        {
                            "path": reference_start_paths[variant],
                            "json_content": {
                                "scenario_id": identity("scenario_id"),
                                "variant_id": variant,
                                "phase": "boundary",
                                "reset_snapshot_sha256": file_hash(
                                    reset_paths[variant]
                                ),
                                "state": "failed",
                            },
                        }
                        for variant in self.variants
                    ],
                    *[
                        {
                            "path": trace_paths[variant],
                            "json_content": {
                                "scenario_id": identity("scenario_id"),
                                "variant_id": variant,
                                "phase": "reference_trace",
                                "boundary_state_sha256": file_hash(
                                    boundary_paths[variant]
                                ),
                                "input_envelope_sha256": dependencies(
                                    "reference_bundle"
                                ),
                                "steps": ["repair"],
                            },
                        }
                        for variant in self.variants
                    ],
                    *[
                        {
                            "path": terminal_paths[variant],
                            "json_content": {
                                "scenario_id": identity("scenario_id"),
                                "variant_id": variant,
                                "phase": "terminal",
                                "boundary_state_sha256": file_hash(
                                    boundary_paths[variant]
                                ),
                                "evaluator_envelope_sha256": envelope_hash(
                                    "evaluator"
                                ),
                                "evaluation": {
                                    "passed": True,
                                    "components": {"goal": True},
                                    "checks": {"goal-complete": True},
                                    "diagnostics": {},
                                    "failures": [],
                                },
                                "final_evidence": {"status": "complete"},
                                "status": "complete",
                            },
                        }
                        for variant in self.variants
                    ],
                ],
            },
            "raw_run_archive": {
                "primary_payload": {
                    "runs": [
                        {
                            "run_id": f"control-{variant}",
                            "variant_id": variant,
                            "run_path": raw_paths[variant],
                            "run_sha256": file_hash(raw_paths[variant]),
                            "raw_trajectory_path": (
                                trajectory_paths[variant]
                            ),
                            "raw_trajectory_sha256": file_hash(
                                trajectory_paths[variant]
                            ),
                            "pre_model_boundary_evidence_path": (
                                pre_model_paths[variant]
                            ),
                            "pre_model_boundary_evidence_sha256": (
                                file_hash(pre_model_paths[variant])
                            ),
                            "summary_report_path": report_paths[variant],
                            "boundary_state_sha256": file_hash(
                                boundary_paths[variant]
                            ),
                            "formal_input_lock_sha256": {
                                "$formal_input_lock_sha256": True
                            },
                            "execution_control": True,
                            "passed": True,
                        }
                        for variant in self.variants
                    ]
                },
                "support_files": [
                    *[
                        {
                            "path": pre_model_paths[variant],
                            "json_content": {
                                "scenario_id": identity("scenario_id"),
                                "variant_id": variant,
                                "phase": "boundary",
                                "reset_snapshot_sha256": file_hash(
                                    reset_paths[variant]
                                ),
                                "state": "failed",
                            },
                        }
                        for variant in self.variants
                    ],
                    *[
                        {
                            "path": trajectory_paths[variant],
                            "json_content": {
                                "scenario_id": identity("scenario_id"),
                                "instance_id": identity("instance_id"),
                                "family": identity("family_id"),
                                "domain": identity("domain_id"),
                                "variant": variant,
                                "run_id": f"control-{variant}",
                                "execution_control": True,
                                "evaluation": {
                                    "passed": True,
                                    "components": {"goal": True},
                                    "checks": {"goal-complete": True},
                                    "diagnostics": {},
                                    "failures": [],
                                },
                                "final_evidence": {
                                    "status": "complete"
                                },
                                "formal_input_lock": {
                                    "$formal_input_lock_verification": (
                                        variant
                                    )
                                },
                                "pre_model_boundary_evidence": {
                                    "variant_id": variant,
                                    "source_basename": (
                                        f"boundary-{variant}.json"
                                    ),
                                    "sha256": file_hash(
                                        pre_model_paths[variant]
                                    ),
                                },
                            },
                        }
                        for variant in self.variants
                    ],
                    *[
                        {
                            "path": raw_paths[variant],
                            "json_content": {
                                "scenario_id": identity("scenario_id"),
                                "variant_id": variant,
                                "run_id": f"control-{variant}",
                                "boundary_state_sha256": file_hash(
                                    boundary_paths[variant]
                                ),
                                "input_envelope_sha256": dependencies(
                                    "raw_run_archive"
                                ),
                                "formal_input_lock_sha256": {
                                    "$formal_input_lock_sha256": True
                                },
                                "raw_trajectory_path": (
                                    trajectory_paths[variant]
                                ),
                                "raw_trajectory_sha256": file_hash(
                                    trajectory_paths[variant]
                                ),
                                "pre_model_boundary_evidence_path": (
                                    pre_model_paths[variant]
                                ),
                                "pre_model_boundary_evidence_sha256": (
                                    file_hash(pre_model_paths[variant])
                                ),
                                "summary_report_path": (
                                    report_paths[variant]
                                ),
                                "execution_control": True,
                                "passed": True,
                            },
                        }
                        for variant in self.variants
                    ],
                ],
            },
            "execution_control": {
                "primary_payload": {
                    "run_ids": [
                        f"control-{variant}" for variant in self.variants
                    ],
                    "completed_runs": len(self.variants),
                    "passed_runs": len(self.variants),
                    "task_pass_rate": 1.0,
                    "formal_input_lock_sha256": {
                        "$formal_input_lock_sha256": True
                    },
                    "control_summary_path": summary_path,
                    "control_summary_sha256": file_hash(summary_path),
                },
                "support_files": [
                    {
                        "path": summary_path,
                        "json_content": {
                            "completed_runs": len(self.variants),
                            "run_errors": [],
                            "task_pass_rate": 1.0,
                            "execution_control_counts": {
                                "true": len(self.variants)
                            },
                            "reports": [
                                {
                                    "scenario_id": identity("scenario_id"),
                                    "variant": variant,
                                    "passed": True,
                                    "path": report_paths[variant],
                                }
                                for variant in self.variants
                            ],
                        },
                    }
                ],
            },
        }
        return {
            "schema_version": "1.0",
            "benchmark_release_id": "release-1",
            "scenario_path": scenario_path,
            "scenario_id": "scenario-1",
            "domain_id": "forgejo",
            "family_id": "family-1",
            "instance_id": "dev-001",
            "variant_ids": list(self.variants),
            "producer_commit": self.commit,
            "output_directory": output,
            "roles": roles,
        }

    def _completed_validation_arguments(
        self,
        root: Path,
        result: Any,
        *,
        require_trusted_evaluator: bool = False,
    ) -> dict[str, object]:
        return {
            "root": root,
            "declarations": result.formal_evidence,
            "benchmark_release_id": "release-1",
            "scenario_id": "scenario-1",
            "domain_id": "forgejo",
            "family_id": "family-1",
            "instance_id": "dev-001",
            "variants": self.variants,
            "control_evidence_path": str(
                result.control_evidence["path"]
            ),
            "control_evidence_sha256": str(
                result.control_evidence["sha256"]
            ),
            "declarations_manifest_path": (
                result.declarations_manifest_path
            ),
            "declarations_manifest_sha256": (
                result.declarations_manifest_sha256
            ),
            "require_trusted_evaluator": require_trusted_evaluator,
        }

    def test_builds_package_accepted_by_authoritative_validator(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._spec(root)
            result = build_formal_evidence(
                spec,
                root=root,
                trusted_producer_commit=self.commit,
            )
            manifest = load_json_strict(
                root / result.declarations_manifest_path
            )
            self.assertEqual(
                manifest["formal_evidence"],
                result.formal_evidence,
            )
            self.assertTrue(
                validate_formal_evidence_roles(
                    **self._completed_validation_arguments(
                        root,
                        result,
                    )
                )
            )
            self.assertEqual(
                sorted(
                    path.name
                    for path in root.glob(".af[ic]-*")
                ),
                [],
            )

    def test_completed_validator_binds_the_declarations_manifest(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = build_formal_evidence(
                self._spec(root),
                root=root,
                trusted_producer_commit=self.commit,
            )
            manifest_path = root / result.declarations_manifest_path
            manifest = load_json_strict(manifest_path)
            manifest["formal_evidence"]["raw_run_archive"]["sha256"] = (
                "0" * 64
            )
            self._write_json(manifest_path, manifest)
            arguments = self._completed_validation_arguments(root, result)
            arguments["declarations_manifest_sha256"] = file_sha256(
                manifest_path
            )
            self.assertFalse(validate_formal_evidence_roles(**arguments))

    def test_completion_rejects_raw_trajectory_without_full_lock(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._spec(root)
            trajectory = next(
                item
                for item in spec["roles"]["raw_run_archive"][
                    "support_files"
                ]
                if "trajectory-a.json" in item["path"]
            )
            trajectory["json_content"]["formal_input_lock"] = {}
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "raw trajectory is not causally bound",
            ):
                build_formal_evidence(
                    spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )

    def test_completion_rejects_pre_model_boundary_tampering(self) -> None:
        for mutation in ("path", "bytes", "hash", "trajectory"):
            with self.subTest(mutation=mutation), TemporaryDirectory() as temporary:
                root = Path(temporary)
                spec = self._spec(root)
                raw_role = spec["roles"]["raw_run_archive"]
                run = raw_role["primary_payload"]["runs"][0]
                trajectory_path = run["raw_trajectory_path"]
                pre_model_path = run[
                    "pre_model_boundary_evidence_path"
                ]
                if mutation == "path":
                    run["pre_model_boundary_evidence_path"] = (
                        trajectory_path
                    )
                    run["pre_model_boundary_evidence_sha256"] = {
                        "$file_sha256": trajectory_path
                    }
                elif mutation == "bytes":
                    pre_model = next(
                        item
                        for item in raw_role["support_files"]
                        if item["path"] == pre_model_path
                    )
                    pre_model["json_content"]["state"] = "different"
                elif mutation == "hash":
                    run["pre_model_boundary_evidence_sha256"] = {
                        "$file_sha256": trajectory_path
                    }
                else:
                    trajectory = next(
                        item
                        for item in raw_role["support_files"]
                        if item["path"] == trajectory_path
                    )
                    boundary_path = spec["roles"]["boundary_bundle"][
                        "primary_payload"
                    ]["variants"][0]["boundary_state_path"]
                    trajectory["json_content"][
                        "pre_model_boundary_evidence"
                    ]["sha256"] = {"$file_sha256": boundary_path}
                    trajectory["json_content"][
                        "pre_model_boundary_evidence"
                    ]["variant_id"] = "b"
                with self.assertRaises(FormalEvidenceBuildError):
                    build_formal_evidence(
                        spec,
                        root=root,
                        trusted_producer_commit=self.commit,
                    )

    def test_release_evaluator_recomputes_reference_and_raw_evidence(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = build_formal_evidence(
                self._spec(root),
                root=root,
                trusted_producer_commit=self.commit,
            )
            strict = self._completed_validation_arguments(
                root,
                result,
                require_trusted_evaluator=True,
            )
            self.assertTrue(validate_formal_evidence_roles(**strict))
            with patch.dict(
                TRUSTED_FORMAL_EVALUATORS,
                {},
                clear=True,
            ):
                self.assertFalse(validate_formal_evidence_roles(**strict))

        for target in ("reference", "raw-final", "raw-boolean"):
            with self.subTest(target=target), TemporaryDirectory() as temporary:
                root = Path(temporary)
                spec = self._spec(root)
                if target == "reference":
                    terminal = next(
                        item
                        for item in spec["roles"]["reference_bundle"][
                            "support_files"
                        ]
                        if "terminal-a.json" in item["path"]
                    )
                    terminal["json_content"]["final_evidence"] = {
                        "status": "incomplete"
                    }
                else:
                    trajectory = next(
                        item
                        for item in spec["roles"]["raw_run_archive"][
                            "support_files"
                        ]
                        if "trajectory-a.json" in item["path"]
                    )
                    if target == "raw-final":
                        trajectory["json_content"]["final_evidence"] = {
                            "status": "incomplete"
                        }
                    else:
                        trajectory["json_content"]["evaluation"][
                            "components"
                        ]["goal"] = False
                with self.assertRaisesRegex(
                    FormalEvidenceBuildError,
                    "authoritative formal validator",
                ):
                    build_formal_evidence(
                        spec,
                        root=root,
                        trusted_producer_commit=self.commit,
                    )

    def test_inputs_phase_is_a_five_role_pre_provider_lock(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._spec(root)
            raw_support = spec["roles"]["raw_run_archive"][
                "support_files"
            ][0]
            raw_support.pop("json_content")
            raw_support["source_path"] = "data/model-runs/not-yet.json"
            result = build_formal_inputs(
                spec,
                root=root,
                trusted_producer_commit=self.commit,
            )
            output = root / spec["output_directory"]
            lock_path = root / result.input_lock_path
            lock = load_json_strict(lock_path)
            rendered_lock = lock_path.read_text(encoding="utf-8")
            self.assertEqual(
                set(lock["input_role_declarations"]),
                {
                    "tool_contract",
                    "evaluator",
                    "reset_evidence",
                    "boundary_bundle",
                    "reference_bundle",
                },
            )
            self.assertNotIn("raw_run_archive", rendered_lock)
            self.assertNotIn("execution_control", rendered_lock)
            self.assertFalse((output / "completion").exists())
            self.assertFalse(
                (output / "completion" / "declarations.json").exists()
            )

    def test_complete_preserves_inputs_and_lock_verifies_before_provider(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._spec(root)
            input_result = build_formal_inputs(
                spec,
                root=root,
                trusted_producer_commit=self.commit,
            )
            output = root / spec["output_directory"]
            before = self._snapshot(output)
            boundary = spec["roles"]["boundary_bundle"][
                "primary_payload"
            ]["variants"][0]
            prefix_path = spec["roles"]["reset_evidence"][
                "primary_payload"
            ]["prefix_path"]
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "not the variant bound",
            ):
                verify_formal_input_lock(
                    root / input_result.input_lock_path,
                    root=root,
                    scenario_id="scenario-1",
                    domain_id="forgejo",
                    family_id="family-1",
                    instance_id="dev-001",
                    variant_id="a",
                    failure_report_path=root
                    / boundary["failure_surface_path"],
                    prefix_path=root / prefix_path,
                    trusted_producer_commit=self.commit,
                )
            verification = verify_formal_input_lock(
                root / input_result.input_lock_path,
                root=root,
                scenario_id="scenario-1",
                domain_id="forgejo",
                family_id="family-1",
                instance_id="dev-001",
                variant_id="a",
                failure_report_path=root
                / boundary["raw_failure_report_path"],
                prefix_path=root / prefix_path,
                trusted_producer_commit=self.commit,
            )
            self.assertEqual(
                set(verification.input_envelope_sha256),
                set(input_result.input_evidence),
            )
            self.assertEqual(
                verification.failure_report_sha256,
                file_sha256(root / boundary["raw_failure_report_path"]),
            )
            self.assertEqual(
                verification.prefix_sha256,
                file_sha256(root / prefix_path),
            )
            tampered_prefix = root / "data" / "tampered-prefix.json"
            self._write_json(tampered_prefix, {"prefix": "different"})
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "runner prefix is not",
            ):
                verify_formal_input_lock(
                    root / input_result.input_lock_path,
                    root=root,
                    scenario_id="scenario-1",
                    domain_id="forgejo",
                    family_id="family-1",
                    instance_id="dev-001",
                    variant_id="a",
                    failure_report_path=root
                    / boundary["raw_failure_report_path"],
                    prefix_path=tampered_prefix,
                    trusted_producer_commit=self.commit,
                )
            complete_formal_evidence(
                spec,
                root=root,
                trusted_producer_commit=self.commit,
            )
            after = self._snapshot(output)
            self.assertEqual(
                before,
                {
                    path: digest
                    for path, digest in after.items()
                    if not path.startswith("completion/")
                },
            )
            self.assertTrue(
                (output / "completion" / "declarations.json").is_file()
            )

    def test_completion_rejects_tampered_inputs_without_writing(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._spec(root)
            build_formal_inputs(
                spec,
                root=root,
                trusted_producer_commit=self.commit,
            )
            output = root / spec["output_directory"]
            boundary_file = next(
                path
                for path in output.rglob("boundary-a.json")
                if path.is_file()
            )
            boundary_file.write_text('{"tampered":true}\n', encoding="utf-8")
            before = self._snapshot(output)
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "differ from the recomputed input lock",
            ):
                complete_formal_evidence(
                    spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )
            self.assertEqual(before, self._snapshot(output))
            self.assertFalse((output / "completion").exists())

    def test_verifier_recomputes_the_self_contained_projection_hash(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._spec(root)
            result = build_formal_inputs(
                spec,
                root=root,
                trusted_producer_commit=self.commit,
            )
            lock_path = root / result.input_lock_path
            lock = load_json_strict(lock_path)
            lock["input_projection_sha256"] = "0" * 64
            self._write_json(lock_path, lock)
            boundary = spec["roles"]["boundary_bundle"][
                "primary_payload"
            ]["variants"][0]
            prefix_path = spec["roles"]["reset_evidence"][
                "primary_payload"
            ]["prefix_path"]
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "projection hash is invalid",
            ):
                verify_formal_input_lock(
                    lock_path,
                    root=root,
                    scenario_id="scenario-1",
                    domain_id="forgejo",
                    family_id="family-1",
                    instance_id="dev-001",
                    variant_id="a",
                    failure_report_path=root
                    / boundary["raw_failure_report_path"],
                    prefix_path=root / prefix_path,
                    trusted_producer_commit=self.commit,
                )

    def test_two_phase_retries_are_idempotent(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._spec(root)
            first_input = build_formal_inputs(
                spec,
                root=root,
                trusted_producer_commit=self.commit,
            )
            output = root / spec["output_directory"]
            input_snapshot = self._snapshot(output)
            second_input = build_formal_inputs(
                spec,
                root=root,
                trusted_producer_commit=self.commit,
            )
            self.assertEqual(first_input, second_input)
            self.assertEqual(input_snapshot, self._snapshot(output))
            first_complete = complete_formal_evidence(
                spec,
                root=root,
                trusted_producer_commit=self.commit,
            )
            complete_snapshot = self._snapshot(output)
            second_complete = complete_formal_evidence(
                spec,
                root=root,
                trusted_producer_commit=self.commit,
            )
            self.assertEqual(first_complete, second_complete)
            self.assertEqual(complete_snapshot, self._snapshot(output))

    def test_concurrent_phase_publishers_converge_without_overwrite(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._spec(root)

            def publish_inputs() -> object:
                return build_formal_inputs(
                    spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )

            with ThreadPoolExecutor(max_workers=2) as executor:
                input_results = list(
                    executor.map(lambda _: publish_inputs(), range(2))
                )
            self.assertEqual(input_results[0], input_results[1])
            output = root / spec["output_directory"]
            input_snapshot = self._snapshot(output)

            def publish_completion() -> object:
                return complete_formal_evidence(
                    spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )

            with ThreadPoolExecutor(max_workers=2) as executor:
                completion_results = list(
                    executor.map(
                        lambda _: publish_completion(),
                        range(2),
                    )
                )
            self.assertEqual(
                completion_results[0],
                completion_results[1],
            )
            final_snapshot = self._snapshot(output)
            self.assertEqual(
                input_snapshot,
                {
                    path: digest
                    for path, digest in final_snapshot.items()
                    if not path.startswith("completion/")
                },
            )

    def test_rejects_primary_payload_identity_spoof(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._spec(root)
            spec["roles"]["tool_contract"]["primary_payload"][
                "scenario_id"
            ] = "other"
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "generated identity fields",
            ):
                build_formal_evidence(
                    spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )
            self.assertFalse((root / spec["output_directory"]).exists())

    def test_rejects_duplicate_support_output_paths(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._spec(root)
            duplicate = copy.deepcopy(
                spec["roles"]["tool_contract"]["support_files"][0]
            )
            spec["roles"]["tool_contract"]["support_files"].append(
                duplicate
            )
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "duplicate or reserved",
            ):
                build_formal_evidence(
                    spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )

    def test_rejects_missing_source_and_path_traversal(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing_spec = self._spec(root)
            missing_spec["roles"]["tool_contract"]["support_files"][1][
                "source_path"
            ] = "data/build-sources/missing.json"
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "missing or unsafe",
            ):
                build_formal_evidence(
                    missing_spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            traversal_spec = self._spec(root)
            traversal_spec["roles"]["tool_contract"]["support_files"][0][
                "path"
            ] = (
                "data/formal/release-1/scenario-1/roles/"
                "tool_contract/support/../escape.json"
            )
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "canonical path",
            ):
                build_formal_evidence(
                    traversal_spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )

    def test_empty_role_is_not_published(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._spec(root)
            spec["roles"]["tool_contract"] = {
                "primary_payload": {},
                "support_files": [],
            }
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "has no tools",
            ):
                build_formal_evidence(
                    spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )
            self.assertFalse((root / spec["output_directory"]).exists())

    def test_rejects_missing_role_and_caller_supplied_hash(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing_role_spec = self._spec(root)
            missing_role_spec["roles"].pop("evaluator")
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "exactly the seven",
            ):
                build_formal_evidence(
                    missing_role_spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            supplied_hash_spec = self._spec(root)
            supplied_hash_spec["roles"]["tool_contract"][
                "primary_payload"
            ]["tools"][0]["input_schema_sha256"] = "0" * 64
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "builder-generated hash placeholder",
            ):
                build_formal_evidence(
                    supplied_hash_spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            selected_hash_spec = self._spec(root)
            tool = selected_hash_spec["roles"]["tool_contract"][
                "primary_payload"
            ]["tools"][0]
            tool["input_schema_sha256"] = {
                "$bound_json_field": {
                    "path": tool["input_schema_path"],
                    "field": "type",
                }
            }
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "cannot populate a formal hash field",
            ):
                build_formal_evidence(
                    selected_hash_spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )

    def test_boundary_requires_distinct_raw_failure_report_binding(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._spec(root)
            for variant in spec["roles"]["boundary_bundle"][
                "primary_payload"
            ]["variants"]:
                variant.pop("raw_failure_report_path")
                variant.pop("raw_failure_report_sha256")
            spec["roles"]["boundary_bundle"]["support_files"] = [
                item
                for item in spec["roles"]["boundary_bundle"][
                    "support_files"
                ]
                if "raw-failure-" not in item["path"]
            ]
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "input evidence semantics",
            ):
                build_formal_inputs(
                    spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )

    def test_hash_drift_is_detected_after_publication(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = self._spec(root)
            result = build_formal_evidence(
                spec,
                root=root,
                trusted_producer_commit=self.commit,
            )
            schema_path = (
                root
                / spec["output_directory"]
                / "roles"
                / "tool_contract"
                / "support"
                / "input-schema.json"
            )
            schema_path.write_text('{"type":"array"}\n', encoding="utf-8")
            self.assertFalse(
                validate_formal_evidence_roles(
                    root=root,
                    declarations=result.formal_evidence,
                    benchmark_release_id="release-1",
                    scenario_id="scenario-1",
                    domain_id="forgejo",
                    family_id="family-1",
                    instance_id="dev-001",
                    variants=self.variants,
                    control_evidence_path=str(
                        result.control_evidence["path"]
                    ),
                    control_evidence_sha256=str(
                        result.control_evidence["sha256"]
                    ),
                )
            )

    def test_rejects_development_scenario_and_untrusted_commit(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            development_spec = self._spec(root, split="development")
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "public_dev or hidden_test",
            ):
                build_formal_evidence(
                    development_spec,
                    root=root,
                    trusted_producer_commit=self.commit,
                )

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            commit_spec = self._spec(root)
            with self.assertRaisesRegex(
                FormalEvidenceBuildError,
                "trusted repository commit",
            ):
                build_formal_evidence(
                    commit_spec,
                    root=root,
                    trusted_producer_commit="b" * 40,
                )

    def test_strict_loader_rejects_duplicate_json_keys(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "spec.json"
            path.write_text(
                '{"schema_version":"1.0","schema_version":"1.0"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                load_formal_evidence_build_spec(path)


if __name__ == "__main__":
    unittest.main()
