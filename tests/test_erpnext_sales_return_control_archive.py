from __future__ import annotations

import hashlib
import json
import unittest

from aftermath_bench.schema import repository_root


class ERPNextSalesReturnControlArchiveTest(unittest.TestCase):
    def test_control_archive_is_complete_and_hash_verified(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "erpnext-sales-return-control-20260730"
        )
        control = json.loads(
            (root / "control.json").read_text(encoding="utf-8")
        )
        self.assertTrue(control["execution_control"])
        self.assertFalse(control["credentials_present"])
        self.assertEqual(control["completed_runs"], 4)
        self.assertEqual(control["task_pass_rate"], 1.0)
        self.assertGreaterEqual(
            control["task_pass_rate"],
            control["control_min_pass_rate"],
        )
        self.assertEqual(len(control["reports"]), 4)
        for report in control["reports"]:
            self.assertTrue(report["passed"])
            for kind in ("trajectory", "failure"):
                path = root / report[f"{kind}_file"]
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    report[f"{kind}_sha256"],
                )
            trajectory = json.loads(
                (root / report["trajectory_file"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(trajectory["execution_control"])
            self.assertEqual(
                trajectory["trajectory_diagnostics"]["tool_error_count"],
                0,
            )
            self.assertTrue(trajectory["evaluation"]["passed"])

        for relative, expected_hash in control["supporting_files"].items():
            self.assertEqual(
                hashlib.sha256((root / relative).read_bytes()).hexdigest(),
                expected_hash,
            )


if __name__ == "__main__":
    unittest.main()
