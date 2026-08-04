from __future__ import annotations

import hashlib
import json
import unittest

from aftermath_bench.schema import repository_root


class ERPNextSharedBatchOrdinaryArchiveTest(unittest.TestCase):
    def test_frozen_glm52_group_records_protocol_not_goal_failures(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "erpnext-shared-batch-ordinary-glm52-20260804"
        )
        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["completed_runs"], 4)
        self.assertEqual(summary["task_pass_rate"], 0.5)
        self.assertEqual(summary["matched_group_success_rate"], 0.0)
        self.assertEqual(summary["component_pass_rates"]["goal_completion"], 1.0)
        self.assertEqual(summary["component_pass_rates"]["preservation"], 1.0)
        self.assertEqual(summary["component_pass_rates"]["protocol_safety"], 0.5)
        self.assertEqual(summary["failure_type_counts"], {"execution_failure": 2})

    def test_manifest_binds_every_frozen_trajectory(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "erpnext-shared-batch-ordinary-glm52-20260804"
        )
        manifest = json.loads((root / "files.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["file_count"], 6)
        for record in manifest["files"]:
            payload = (root / record["path"]).read_bytes()
            self.assertEqual(len(payload), record["bytes"])
            self.assertEqual(hashlib.sha256(payload).hexdigest(), record["sha256"])


if __name__ == "__main__":
    unittest.main()
