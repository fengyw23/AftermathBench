from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.benchmark_matrix import (
    benchmark_family_index,
    load_benchmark_matrix,
)
from aftermath_bench.native_freeze import (
    append_usage_event,
    build_frozen_bundle,
)
from aftermath_bench.native_scenario import NativeScenario, load_native_scenario
from aftermath_bench.release_manifest import (
    FORMAL_EVIDENCE_DEPENDENCIES,
    FORMAL_EVIDENCE_ROLES,
    _validate_control_summary,
    _validate_hidden_bundle,
    _validate_variant_semantics,
    default_release_manifest_path,
    derive_release_state,
    file_sha256,
    load_release_manifest,
    validate_formal_evidence_roles,
    validate_release_manifest,
)
from aftermath_bench.schema import repository_root


class ReleaseManifestTest(unittest.TestCase):
    def test_current_checkpoint_binds_only_verified_development_candidates(
        self,
    ) -> None:
        report = validate_release_manifest(
            load_release_manifest(default_release_manifest_path())
        )
        self.assertTrue(report.passed, report.failures)
        self.assertEqual(report.release_state, "development_only")
        self.assertEqual(
            report.observed["hard_development_candidate_count"], 2
        )
        self.assertEqual(
            report.observed["hard_development_candidate_case_count"], 21
        )
        self.assertEqual(report.observed["formal_verified_slot_count"], 0)
        self.assertEqual(report.observed["missing_formal_slot_count"], 36)

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

    def test_formal_evidence_requires_distinct_cross_bound_envelopes(
        self,
    ) -> None:
        release_id = "release-1"
        variants = ("a", "b")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "data" / "evidence"
            evidence.mkdir(parents=True)
            declarations: dict[str, dict[str, str]] = {}
            role_order = (
                "tool_contract",
                "evaluator",
                "reset_evidence",
                "boundary_bundle",
                "reference_bundle",
                "raw_run_archive",
                "execution_control",
            )
            for role in role_order:
                payload = evidence / f"{role}-payload.json"
                payload.write_text(
                    json.dumps({"role": role}),
                    encoding="utf-8",
                )
                envelope = evidence / f"{role}-envelope.json"
                envelope.write_text(
                    json.dumps(
                        {
                            "schema_version": "1.0",
                            "artifact_type": role,
                            "benchmark_release_id": release_id,
                            "scenario_id": "scenario-1",
                            "domain_id": "forgejo",
                            "family_id": "family-1",
                            "instance_id": "dev-001",
                            "variant_ids": list(variants),
                            "producer_commit": "a" * 40,
                            "depends_on": {
                                dependency: declarations[dependency][
                                    "sha256"
                                ]
                                for dependency in (
                                    FORMAL_EVIDENCE_DEPENDENCIES[role]
                                )
                            },
                            "files": [
                                {
                                    "path": (
                                        "data/evidence/"
                                        f"{role}-payload.json"
                                    ),
                                    "sha256": file_sha256(payload),
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                declarations[role] = {
                    "path": f"data/evidence/{role}-envelope.json",
                    "sha256": file_sha256(envelope),
                }
            arguments = {
                "root": root,
                "declarations": declarations,
                "benchmark_release_id": release_id,
                "scenario_id": "scenario-1",
                "domain_id": "forgejo",
                "family_id": "family-1",
                "instance_id": "dev-001",
                "variants": variants,
            }
            self.assertTrue(validate_formal_evidence_roles(**arguments))
            repeated = {
                role: dict(declarations["boundary_bundle"])
                for role in FORMAL_EVIDENCE_ROLES
            }
            self.assertFalse(
                validate_formal_evidence_roles(
                    **{**arguments, "declarations": repeated}
                )
            )

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
