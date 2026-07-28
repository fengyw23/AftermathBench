import unittest

from aftermath_bench.runtime_gate import (
    load_runtime_manifest,
    runtime_manifest_paths,
    validate_runtime_manifest,
)


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

    def test_erpnext_passes_source_gate_but_not_execution_gate_yet(self) -> None:
        report = next(
            validate_runtime_manifest(load_runtime_manifest(path))
            for path in runtime_manifest_paths()
            if path.parent.name == "erpnext-v15"
        )
        self.assertTrue(report.source_audit_passed)
        self.assertFalse(report.execution_admitted)


if __name__ == "__main__":
    unittest.main()

