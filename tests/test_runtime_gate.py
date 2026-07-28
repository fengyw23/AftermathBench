import json
import unittest

from aftermath_bench.runtime_gate import (
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

    def test_erpnext_passes_source_and_execution_gates(self) -> None:
        report = next(
            validate_runtime_manifest(load_runtime_manifest(path))
            for path in runtime_manifest_paths()
            if path.parent.name == "erpnext-v15"
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


if __name__ == "__main__":
    unittest.main()
