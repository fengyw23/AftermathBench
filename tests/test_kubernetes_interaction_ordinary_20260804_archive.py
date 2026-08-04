from __future__ import annotations

import json
import unittest

from aftermath_bench.evidence_manifest import build_file_manifest
from aftermath_bench.schema import repository_root


class KubernetesInteractionOrdinary20260804ArchiveTest(unittest.TestCase):
    def test_archive_has_complete_non_replacing_coverage(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "kubernetes-interaction-ordinary-glm52-20260804"
        )
        coverage = json.loads(
            (root / "coverage-manifest.json").read_text(encoding="utf-8")
        )
        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        analysis = json.loads((root / "analysis.json").read_text(encoding="utf-8"))
        files = json.loads((root / "files.json").read_text(encoding="utf-8"))

        self.assertEqual(coverage["primary_run_id"], "30865035666")
        self.assertEqual(coverage["retry_run_ids"], ["30872359883"])
        self.assertEqual(coverage["missing_primary_variants"], ["state_01", "state_02"])
        self.assertEqual(coverage["trajectory_count"], 13)
        self.assertEqual(len({row["variant"] for row in coverage["trajectories"]}), 13)
        self.assertTrue(
            all(
                not row["source_path"].startswith(("/", "D:\\"))
                for row in coverage["trajectories"]
            )
        )
        self.assertEqual(summary["completed_runs"], 13)
        self.assertEqual(summary["run_errors"], [])
        self.assertAlmostEqual(summary["task_pass_rate"], 2 / 13)
        self.assertEqual(summary["failure_type_counts"], {"scope_failure": 11})
        self.assertEqual(analysis["completed_runs"], 13)
        self.assertEqual(analysis["primary_error_counts"], {"scope_failure": 11})

        rebuilt = build_file_manifest(root, exclude={"files.json"})
        self.assertEqual(files, rebuilt)


if __name__ == "__main__":
    unittest.main()
