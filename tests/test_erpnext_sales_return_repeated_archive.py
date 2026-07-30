from __future__ import annotations

import hashlib
import json
import unittest

from aftermath_bench.schema import repository_root


class ERPNextSalesReturnRepeatedArchiveTest(unittest.TestCase):
    def test_composite_has_twenty_valid_selected_trajectories(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "erpnext-sales-return-ordinary-repeat5-20260730"
        )
        audit = json.loads((root / "audit.json").read_text(encoding="utf-8"))
        selection = json.loads(
            (root / "selection.json").read_text(encoding="utf-8")
        )
        self.assertFalse(audit["credentials_present"])
        self.assertEqual(audit["completed_runs"], 20)
        self.assertEqual(audit["logical_repetitions"], 5)
        self.assertEqual(audit["excluded_provider_failure_count"], 1)
        self.assertEqual(audit["provider_or_runtime_error_count_in_score"], 0)
        self.assertEqual(audit["tool_error_count"], 0)

        variants = (
            "request_not_reached",
            "database_committed_response_lost",
            "after_commit_enqueue_failed",
            "async_job_pending",
        )
        reports = []
        for repetition in range(1, 6):
            for variant in variants:
                if repetition == 3 and variant == (
                    "after_commit_enqueue_failed"
                ):
                    relative = selection["replacement"]["trajectory"]
                else:
                    relative = (
                        "primary-run/model-runs/"
                        f"repetition-{repetition:02d}/{variant}.json"
                    )
                path = root / relative
                self.assertTrue(path.is_file(), relative)
                report = json.loads(path.read_text(encoding="utf-8"))
                self.assertFalse(report["execution_control"])
                self.assertEqual(
                    report["trajectory_diagnostics"]["tool_error_count"],
                    0,
                )
                reports.append(report)

        self.assertEqual(len(reports), 20)
        self.assertEqual(sum(row["evaluation"]["passed"] for row in reports), 13)
        self.assertEqual(audit["task_pass_rate"], 13 / 20)
        for component in (
            "goal_completion",
            "repair_completeness",
            "preservation",
        ):
            self.assertTrue(
                all(row["evaluation"]["components"][component] for row in reports)
            )
        failed = [row for row in reports if not row["evaluation"]["passed"]]
        self.assertEqual(len(failed), 7)
        for report in failed:
            false_checks = {
                name
                for name, passed in report["evaluation"]["checks"].items()
                if not passed
            }
            self.assertEqual(
                false_checks,
                {"no_duplicate_replacement_invoice"},
            )
            self.assertTrue(
                report["trajectory_diagnostics"][
                    "created_invoice_without_linked_invoice_investigation"
                ]
            )

        prefix_hashes = {
            hashlib.sha256(
                (root / directory / "prefix.json").read_bytes()
            ).hexdigest()
            for directory in ("primary-run", "infrastructure-retry")
        }
        self.assertEqual(prefix_hashes, {audit["prefix_sha256"]})
        self.assertEqual(
            audit["paired_execution_control"]["prefix_sha256"],
            audit["prefix_sha256"],
        )

    def test_archive_manifest_is_byte_verified(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "erpnext-sales-return-ordinary-repeat5-20260730"
        )
        audit = json.loads((root / "audit.json").read_text(encoding="utf-8"))
        manifest_path = root / audit["file_manifest"]
        self.assertEqual(
            hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            audit["file_manifest_sha256"],
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["excluded_files"],
            ["README.md", "audit.json", "files.json"],
        )
        for entry in manifest["files"]:
            path = root / entry["path"]
            self.assertEqual(path.stat().st_size, entry["bytes"])
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                entry["sha256"],
            )


if __name__ == "__main__":
    unittest.main()
