from __future__ import annotations

import hashlib
import json
import unittest

from aftermath_bench.schema import repository_root


class KubernetesValidControlArchiveTest(unittest.TestCase):
    def test_replacement_control_is_complete_and_deterministic(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "kubernetes-interaction-control-valid-20260730"
        )
        audit = json.loads((root / "audit.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["classification"], "valid_execution_control")
        self.assertFalse(audit["credentials_present"])
        self.assertTrue(audit["execution_control"])
        self.assertEqual(audit["completed_runs"], 13)
        self.assertEqual(audit["task_pass_rate"], 12 / 13)
        self.assertGreaterEqual(
            audit["task_pass_rate"],
            audit["control_min_pass_rate"],
        )
        self.assertEqual(audit["provider_or_runtime_error_count"], 0)
        self.assertEqual(audit["tool_error_count"], 0)
        self.assertEqual(audit["rescore_changed_run_count"], 0)

        summary = json.loads(
            (root / "model-runs" / "summary.json").read_text(encoding="utf-8")
        )
        analysis = json.loads(
            (root / "model-runs" / "analysis.json").read_text(encoding="utf-8")
        )
        rescore = json.loads(
            (root / "model-runs" / "rescore.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["completed_runs"], 13)
        self.assertEqual(summary["run_errors"], [])
        self.assertEqual(summary["task_pass_rate"], 12 / 13)
        self.assertEqual(analysis["load_errors"], [])
        self.assertEqual(analysis["failed_check_counts"], {
            "candidate_artifacts_match_commit": 1,
        })
        self.assertEqual(analysis["protocol_violation_counts"], {})
        self.assertEqual(analysis["unexpected_external_key_counts"], {})
        self.assertEqual(analysis["missing_external_key_counts"], {})
        self.assertEqual(rescore["changed_run_count"], 0)
        failed = [row for row in rescore["reports"] if not row["rescored_passed"]]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["variant"], "state_02")
        self.assertEqual(
            failed[0]["rescored_failures"],
            ["candidate_artifacts_match_commit"],
        )

        self.assertEqual(
            hashlib.sha256((root / "prefix.json").read_bytes()).hexdigest(),
            audit["prefix_sha256"],
        )

    def test_archive_manifest_is_byte_verified(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "kubernetes-interaction-control-valid-20260730"
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
        self.assertEqual(manifest["file_count"], 31)
        for entry in manifest["files"]:
            path = root / entry["path"]
            self.assertEqual(path.stat().st_size, entry["bytes"])
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                entry["sha256"],
            )


if __name__ == "__main__":
    unittest.main()
