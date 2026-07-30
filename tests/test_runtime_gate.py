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
            reports = []
            for index in range(4):
                boundary = root / f"boundary-{index}.json"
                reference = root / f"reference-{index}.json"
                boundary.write_text("{}", encoding="utf-8")
                reference.write_text("{}", encoding="utf-8")
                reports.append(
                    {
                        "variant": f"v{index}",
                        "boundary_file": boundary.name,
                        "boundary_sha256": hashlib.sha256(
                            boundary.read_bytes()
                        ).hexdigest(),
                        "reference_file": reference.name,
                        "reference_sha256": hashlib.sha256(
                            reference.read_bytes()
                        ).hexdigest(),
                        "boundary_validation_passed": True,
                        "reference_recovery_passed": False,
                    }
                )
            manifest = root / "admission.json"
            manifest.write_text(
                json.dumps(
                    {
                        "runtime_id": "runtime-1",
                        "head_sha": "a" * 40,
                        "workflow_run_url": (
                            "https://github.com/example/repo/actions/runs/1"
                        ),
                        "credentials_present": False,
                        "reports": reports,
                    }
                ),
                encoding="utf-8",
            )
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
