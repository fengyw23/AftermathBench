import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.runtime_gate import (
    _evidence_manifest_consistent,
    _report_passed,
    load_runtime_manifest,
    runtime_manifest_paths,
    validate_runtime_manifest,
)
from aftermath_bench.schema import repository_root


def _write_phase_payload(
    path: Path,
    *,
    runtime_id: str,
    scenario_id: str,
    variant_id: str,
    phase: str,
    passed: bool = True,
) -> None:
    payload = {
        "schema_version": "test",
        "scenario_id": scenario_id,
        "variant": variant_id,
    }
    if phase == "boundary":
        payload.update(
            {
                "surface_result": "connection lost",
                "checks": {"boundary_valid": passed},
                "passed": passed,
            }
        )
    else:
        payload.update(
            {
                "control": "state_driven_reference",
                "reference_trace": [{"tool": "inspect_state"}],
                "evaluation": {"passed": passed},
            }
        )
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_combined_manifest(
    root: Path,
) -> tuple[Path, dict]:
    runtime_id = "runtime-1"
    scenario_id = "scenario-1"
    reports = []
    for index in range(4):
        variant = f"v{index}"
        boundary = root / f"boundary-{index}.json"
        reference = root / f"reference-{index}.json"
        _write_phase_payload(
            boundary,
            runtime_id=runtime_id,
            scenario_id=scenario_id,
            variant_id=variant,
            phase="boundary",
        )
        _write_phase_payload(
            reference,
            runtime_id=runtime_id,
            scenario_id=scenario_id,
            variant_id=variant,
            phase="reference",
        )
        reports.append(
            {
                "variant": variant,
                "boundary_file": boundary.name,
                "boundary_sha256": hashlib.sha256(
                    boundary.read_bytes()
                ).hexdigest(),
                "reference_file": reference.name,
                "reference_sha256": hashlib.sha256(
                    reference.read_bytes()
                ).hexdigest(),
                "boundary_validation_passed": True,
                "reference_recovery_passed": True,
            }
        )
    payload = {
        "runtime_id": runtime_id,
        "head_sha": "a" * 40,
        "workflow_run_url": (
            "https://github.com/example/repo/actions/runs/1"
        ),
        "credentials_present": False,
        "evidence_contract": {
            "schema_version": "1.0",
            "scenario_id": scenario_id,
            "phases": {
                "boundary": {
                    "file_field": "boundary_file",
                    "sha256_field": "boundary_sha256",
                    "pass_field": "boundary_validation_passed",
                },
                "reference": {
                    "file_field": "reference_file",
                    "sha256_field": "reference_sha256",
                    "pass_field": "reference_recovery_passed",
                },
            },
        },
        "reports": reports,
    }
    manifest = root / "admission.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return manifest, payload


class RuntimeGateTest(unittest.TestCase):
    def test_runtime_declarations_are_truthful(self) -> None:
        reports = [
            validate_runtime_manifest(load_runtime_manifest(path))
            for path in runtime_manifest_paths()
        ]
        self.assertGreaterEqual(len(reports), 2)
        for report in reports:
            with self.subTest(runtime=report.runtime_id):
                self.assertNotIn("source_status_truthful", report.failures)
                self.assertNotIn("execution_status_truthful", report.failures)

    def test_enterpriseops_is_rejected_for_final_runtime_use(self) -> None:
        report = next(
            validate_runtime_manifest(load_runtime_manifest(path))
            for path in runtime_manifest_paths()
            if path.parent.name == "enterpriseops-prototype"
        )
        self.assertFalse(report.source_audit_passed)
        self.assertFalse(report.execution_admitted)

    def test_erpnext_source_passes_but_unarchived_raw_evidence_is_rejected(
        self,
    ) -> None:
        report = next(
            validate_runtime_manifest(load_runtime_manifest(path))
            for path in runtime_manifest_paths()
            if path.parent.name == "erpnext-v15"
        )
        self.assertTrue(report.source_audit_passed)
        self.assertFalse(report.execution_admitted)
        self.assertFalse(
            report.execution_checks["boundary_evidence_files_verified"]
        )
        self.assertFalse(
            report.execution_checks["reference_evidence_files_verified"]
        )

    def test_forgejo_passes_source_and_execution_gates(self) -> None:
        report = next(
            validate_runtime_manifest(load_runtime_manifest(path))
            for path in runtime_manifest_paths()
            if path.parent.name == "forgejo-main"
        )
        self.assertTrue(report.source_audit_passed)
        self.assertTrue(report.execution_admitted)
        self.assertFalse(report.failures)

    def test_kubernetes_passes_source_and_execution_gates(self) -> None:
        report = next(
            validate_runtime_manifest(load_runtime_manifest(path))
            for path in runtime_manifest_paths()
            if path.parent.name == "kubernetes-v1.34"
        )
        self.assertTrue(report.source_audit_passed)
        self.assertTrue(report.execution_admitted)
        self.assertTrue(
            report.execution_checks["admission_evidence_recorded"]
        )
        self.assertFalse(report.failures)

    def test_erpnext_admission_manifest_records_all_four_reports(self) -> None:
        path = (
            repository_root()
            / "data"
            / "evidence"
            / "erpnext-native-20260728"
            / "admission.json"
        )
        evidence = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(evidence["credentials_present"])
        reports = evidence["reports"]
        self.assertEqual(
            {report["variant"] for report in reports},
            {
                "request_not_reached",
                "database_committed_response_lost",
                "after_commit_enqueue_failed",
                "async_job_pending",
            },
        )
        self.assertTrue(
            all(report["boundary_validation_passed"] for report in reports)
        )
        self.assertTrue(
            all(len(report["sha256"]) == 64 for report in reports)
        )

    def test_runtime_gate_rejects_mismatched_evidence_identity(self) -> None:
        path = next(
            path
            for path in runtime_manifest_paths()
            if path.parent.name == "erpnext-v15"
        )
        manifest = load_runtime_manifest(path)
        manifest["admission_evidence"] = dict(
            manifest["admission_evidence"],
            head_sha="0" * 40,
        )
        report = validate_runtime_manifest(manifest)
        self.assertFalse(report.execution_admitted)
        self.assertFalse(
            report.execution_checks["admission_evidence_recorded"]
        )

    def test_report_requires_every_named_pass_field(self) -> None:
        self.assertFalse(
            _report_passed(
                {"passed": True},
                ("passed", "reference_recovery_passed"),
            )
        )

    def test_runtime_gate_rejects_evidence_path_escape(self) -> None:
        path = next(
            path
            for path in runtime_manifest_paths()
            if path.parent.name == "erpnext-v15"
        )
        manifest = load_runtime_manifest(path)
        manifest["admission_evidence"] = dict(
            manifest["admission_evidence"],
            evidence_manifest="../outside.json",
        )
        report = validate_runtime_manifest(manifest)
        self.assertFalse(
            report.execution_checks["admission_evidence_recorded"]
        )

    def test_runtime_gate_replays_both_boundary_and_reference_hashes(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, payload = _write_combined_manifest(root)
            for report in payload["reports"]:
                report["reference_recovery_passed"] = False
                report["passed"] = True
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            common = {
                "path": manifest,
                "runtime_id": "runtime-1",
                "head_sha": "a" * 40,
                "workflow_run": (
                    "https://github.com/example/repo/actions/runs/1"
                ),
            }
            self.assertTrue(
                _evidence_manifest_consistent(
                    **common,
                    phase="boundary",
                )
            )
            self.assertFalse(
                _evidence_manifest_consistent(
                    **common,
                    phase="reference",
                )
            )

    def test_runtime_gate_rejects_shared_or_empty_raw_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, payload = _write_combined_manifest(root)
            first = payload["reports"][0]
            second = payload["reports"][1]
            second["boundary_file"] = first["boundary_file"]
            second["boundary_sha256"] = first["boundary_sha256"]
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertFalse(
                _evidence_manifest_consistent(
                    manifest,
                    runtime_id="runtime-1",
                    head_sha="a" * 40,
                    workflow_run=(
                        "https://github.com/example/repo/actions/runs/1"
                    ),
                    phase="boundary",
                )
            )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, payload = _write_combined_manifest(root)
            empty = root / "empty.json"
            empty.write_bytes(b"")
            payload["reports"][0]["boundary_file"] = empty.name
            payload["reports"][0]["boundary_sha256"] = hashlib.sha256(
                empty.read_bytes()
            ).hexdigest()
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertFalse(
                _evidence_manifest_consistent(
                    manifest,
                    runtime_id="runtime-1",
                    head_sha="a" * 40,
                    workflow_run=(
                        "https://github.com/example/repo/actions/runs/1"
                    ),
                    phase="boundary",
                )
            )

    def test_runtime_gate_rejects_cross_variant_and_cross_phase_payloads(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, declaration = _write_combined_manifest(root)
            source = root / declaration["reports"][0]["boundary_file"]
            copied = root / "copied-from-v0.json"
            copied.write_bytes(source.read_bytes())
            report = declaration["reports"][1]
            report["boundary_file"] = copied.name
            report["boundary_sha256"] = hashlib.sha256(
                copied.read_bytes()
            ).hexdigest()
            manifest.write_text(json.dumps(declaration), encoding="utf-8")
            self.assertFalse(
                _evidence_manifest_consistent(
                    manifest,
                    runtime_id="runtime-1",
                    head_sha="a" * 40,
                    workflow_run=(
                        "https://github.com/example/repo/actions/runs/1"
                    ),
                    phase="boundary",
                )
            )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, declaration = _write_combined_manifest(root)
            report = declaration["reports"][0]
            reference = root / report["reference_file"]
            copied = root / "reference-used-as-boundary.json"
            copied.write_bytes(reference.read_bytes())
            report["boundary_file"] = copied.name
            report["boundary_sha256"] = hashlib.sha256(
                copied.read_bytes()
            ).hexdigest()
            manifest.write_text(json.dumps(declaration), encoding="utf-8")
            self.assertFalse(
                _evidence_manifest_consistent(
                    manifest,
                    runtime_id="runtime-1",
                    head_sha="a" * 40,
                    workflow_run=(
                        "https://github.com/example/repo/actions/runs/1"
                    ),
                    phase="boundary",
                )
            )

    def test_runtime_gate_binds_native_payload_identity_and_pass(self) -> None:
        mutations = {
            "scenario_id": "other-scenario",
            "variant": "other-variant",
            "passed": False,
        }
        for field, value in mutations.items():
            with self.subTest(field=field), TemporaryDirectory() as directory:
                root = Path(directory)
                manifest, declaration = _write_combined_manifest(root)
                report = declaration["reports"][0]
                evidence = root / report["boundary_file"]
                payload = json.loads(evidence.read_text(encoding="utf-8"))
                payload[field] = value
                evidence.write_text(json.dumps(payload), encoding="utf-8")
                report["boundary_sha256"] = hashlib.sha256(
                    evidence.read_bytes()
                ).hexdigest()
                manifest.write_text(
                    json.dumps(declaration),
                    encoding="utf-8",
                )
                self.assertFalse(
                    _evidence_manifest_consistent(
                        manifest,
                        runtime_id="runtime-1",
                        head_sha="a" * 40,
                        workflow_run=(
                            "https://github.com/example/repo/actions/runs/1"
                        ),
                        phase="boundary",
                    )
                )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, _ = _write_combined_manifest(root)
            self.assertFalse(
                _evidence_manifest_consistent(
                    manifest,
                    runtime_id="other-runtime",
                    head_sha="a" * 40,
                    workflow_run=(
                        "https://github.com/example/repo/actions/runs/1"
                    ),
                    phase="boundary",
                )
            )

    def test_forgejo_admission_manifest_records_replayable_reports(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "forgejo-native-recovery-control-20260729"
        )
        evidence = json.loads(
            (root / "admission.json").read_text(encoding="utf-8")
        )
        self.assertFalse(evidence["credentials_present"])
        self.assertEqual(evidence["reference_recovery_passed"], "4/4")
        reports = evidence["reports"]
        self.assertEqual(len(reports), 4)
        for report in reports:
            self.assertTrue(report["boundary_validation_passed"])
            self.assertTrue(report["reference_recovery_passed"])
            boundary = root / report["boundary_file"]
            reference = root / report["reference_file"]
            self.assertEqual(
                hashlib.sha256(boundary.read_bytes()).hexdigest(),
                report["boundary_sha256"],
            )
            self.assertEqual(
                hashlib.sha256(reference.read_bytes()).hexdigest(),
                report["reference_sha256"],
            )

    def test_kubernetes_admission_manifest_is_hash_verified(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "kubernetes-native-recovery-control-20260729"
        )
        evidence = json.loads(
            (root / "admission.json").read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["runtime_id"], "kubernetes-v1.34")
        self.assertFalse(evidence["credentials_present"])
        self.assertTrue(evidence["source_build"]["kind_built_from_source"])
        self.assertEqual(len(evidence["reports"]), 4)
        for report in evidence["reports"]:
            self.assertTrue(report["boundary_validation_passed"])
            self.assertTrue(report["reference_recovery_passed"])
            for kind in ("boundary", "reference"):
                path = root / report[f"{kind}_file"]
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    report[f"{kind}_sha256"],
                )
        for relative, expected_hash in evidence["supporting_files"].items():
            self.assertEqual(
                hashlib.sha256((root / relative).read_bytes()).hexdigest(),
                expected_hash,
            )


if __name__ == "__main__":
    unittest.main()
