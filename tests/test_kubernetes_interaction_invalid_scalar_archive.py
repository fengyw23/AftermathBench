from __future__ import annotations

import hashlib
import json
import unittest

from aftermath_bench.schema import repository_root


class KubernetesInvalidScalarArchiveTest(unittest.TestCase):
    def test_invalid_run_and_corrected_rescore_are_preserved(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "kubernetes-interaction-control-invalid-scalar-20260730"
        )
        audit = json.loads(
            (root / "audit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            audit["classification"],
            "invalid_original_score_hidden_scalar_type",
        )
        self.assertFalse(audit["credentials_present"])
        self.assertEqual(audit["completed_runs"], 13)
        self.assertEqual(audit["original_task_pass_rate"], 11 / 13)
        self.assertEqual(audit["rescored_task_pass_rate"], 12 / 13)
        self.assertEqual(audit["changed_variant"], "state_12")
        self.assertEqual(audit["corrected_failures"], [])

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

        rescore = json.loads(
            (root / "model-runs" / "rescore.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(rescore["changed_run_count"], 1)
        changed = next(row for row in rescore["reports"] if row["changed"])
        self.assertEqual(changed["variant"], "state_12")
        self.assertTrue(changed["rescored_passed"])


if __name__ == "__main__":
    unittest.main()
