from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from aftermath_bench.schema import repository_root


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ForgejoPublicationFinalArchivesTest(unittest.TestCase):
    def _verify_manifest(self, root: Path) -> None:
        manifest = _load(root / "files.json")
        self.assertEqual(manifest["excluded_files"], ["files.json"])
        self.assertGreater(manifest["file_count"], 0)
        for entry in manifest["files"]:
            path = root / entry["path"]
            self.assertEqual(path.stat().st_size, entry["bytes"])
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                entry["sha256"],
            )

    def test_native_replay_is_hard_admitted_and_complete(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "forgejo-publication-native-final-20260731"
        )
        admission = _load(root / "scenario" / "artifacts" / "admission.json")
        reference = _load(root / "scenario" / "artifacts" / "reference.json")
        baselines = _load(root / "scenario" / "artifacts" / "baselines.json")

        self.assertTrue(admission["passed"])
        self.assertEqual(admission["admitted_tier"], "hard")
        self.assertEqual(admission["observed"]["successful_prefix_writes"], 21)
        self.assertEqual(admission["observed"]["replayed_relation_count"], 30)
        self.assertEqual(admission["observed"]["semantic_edge_count"], 30)
        self.assertEqual(admission["observed"]["relation_type_count"], 19)
        self.assertEqual(admission["observed"]["dependency_depth"], 6)
        self.assertEqual(
            admission["observed"]["distinct_recovery_signature_count"],
            5,
        )
        self.assertEqual(len(reference["reports"]), 8)
        self.assertTrue(all(report["passed"] for report in reference["reports"]))
        self.assertEqual(baselines["maximum_heuristic_pass_rate"], 0.25)
        self.assertEqual(baselines["matched_group_solvers"], [])
        self._verify_manifest(root)

    def test_execution_control_passes_all_matched_boundaries(self) -> None:
        root = (
            repository_root()
            / "data"
            / "evidence"
            / "forgejo-publication-control-final-20260731"
        )
        summary = _load(root / "model-runs" / "summary.json")
        analysis = _load(root / "analysis.json")

        self.assertEqual(summary["completed_runs"], 8)
        self.assertEqual(summary["run_errors"], [])
        self.assertEqual(summary["task_pass_rate"], 1.0)
        self.assertEqual(summary["matched_group_success_rate"], 1.0)
        self.assertEqual(summary["execution_control_counts"], {"true": 8})
        self.assertEqual(
            summary["component_pass_rates"],
            {
                "goal_completion": 1.0,
                "preservation": 1.0,
                "protocol_safety": 1.0,
                "repair_completeness": 1.0,
            },
        )
        self.assertEqual(analysis["completed_runs"], 8)
        self.assertEqual(analysis["load_errors"], [])
        self.assertEqual(
            analysis["evidence_complete_before_first_write_rate"],
            1.0,
        )
        self.assertEqual(analysis["mutation_tool_error_count"], 0)
        self.assertEqual(
            analysis["derived_failure_stage_counts"],
            {"pass": 8},
        )
        self._verify_manifest(root)


if __name__ == "__main__":
    unittest.main()
