from __future__ import annotations

import hashlib
import json
import unittest

from aftermath_bench.schema import repository_root


class ERPNextSalesReturnOrdinaryArchiveTest(unittest.TestCase):
    def test_ordinary_archive_is_complete_and_hash_verified(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "erpnext-sales-return-ordinary-20260730"
        )
        experiment = json.loads(
            (root / "experiment.json").read_text(encoding="utf-8")
        )
        self.assertFalse(experiment["execution_control"])
        self.assertFalse(experiment["credentials_present"])
        self.assertEqual(experiment["completed_runs"], 4)
        self.assertEqual(experiment["task_pass_rate"], 0.5)
        self.assertEqual(experiment["matched_group_success_rate"], 0.0)
        self.assertEqual(
            experiment["paired_execution_control"]["head_sha"],
            experiment["head_sha"],
        )
        self.assertEqual(
            experiment["paired_execution_control"]["task_pass_rate"],
            1.0,
        )
        self.assertEqual(len(experiment["reports"]), 4)
        self.assertEqual(
            {
                report["failure_subtype"]
                for report in experiment["reports"]
                if report["failure_subtype"]
            },
            {
                "preexisting_downstream_not_queried",
                "post_mutation_state_not_refreshed",
            },
        )
        for report in experiment["reports"]:
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
            self.assertFalse(trajectory["execution_control"])
            self.assertEqual(
                trajectory["trajectory_diagnostics"]["tool_error_count"],
                0,
            )
            self.assertEqual(
                bool(trajectory["evaluation"]["passed"]),
                report["passed"],
            )

        for relative, expected_hash in experiment["supporting_files"].items():
            self.assertEqual(
                hashlib.sha256((root / relative).read_bytes()).hexdigest(),
                expected_hash,
            )


if __name__ == "__main__":
    unittest.main()
