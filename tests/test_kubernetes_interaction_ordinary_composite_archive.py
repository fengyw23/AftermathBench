from __future__ import annotations

import hashlib
import json
import unittest

from aftermath_bench.kubernetes_pairing import task_prefix_sha256
from aftermath_bench.schema import repository_root


class KubernetesOrdinaryCompositeArchiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = (
            repository_root()
            / "data"
            / "evidence"
            / "kubernetes-interaction-ordinary-composite-20260730"
        )

    def test_selected_matrix_is_complete_and_reproducible(self) -> None:
        audit = json.loads(
            (self.root / "audit.json").read_text(encoding="utf-8")
        )
        summary = json.loads(
            (self.root / "selected-runs" / "summary.json").read_text(
                encoding="utf-8"
            )
        )
        analysis = json.loads(
            (self.root / "selected-runs" / "analysis.json").read_text(
                encoding="utf-8"
            )
        )
        rescore = json.loads(
            (self.root / "selected-runs" / "rescore.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(audit["credentials_present"])
        self.assertEqual(audit["provider_or_runtime_error_count_in_score"], 0)
        self.assertEqual(summary["completed_runs"], 13)
        self.assertEqual(summary["run_errors"], [])
        self.assertEqual(summary["task_pass_rate"], 1 / 13)
        self.assertEqual(summary["matched_group_success_rate"], 0)
        self.assertEqual(summary["component_pass_rates"], {
            "goal_completion": 8 / 13,
            "preservation": 12 / 13,
            "protocol_safety": 7 / 13,
            "repair_completeness": 1 / 13,
        })
        self.assertEqual(analysis["primary_error_counts"], {
            "scope_failure": 12,
        })
        self.assertEqual(analysis["protocol_violation_counts"], {})
        self.assertTrue(
            all(value == 13 for value in (
                analysis["evidence_group_observation_counts"].values()
            ))
        )
        self.assertEqual(rescore["changed_run_count"], 0)
        passed = [
            row["variant"]
            for row in rescore["reports"]
            if row["rescored_passed"]
        ]
        self.assertEqual(passed, ["state_06"])

    def test_selection_and_task_state_pairing_are_explicit(self) -> None:
        selection = json.loads(
            (self.root / "selection.json").read_text(encoding="utf-8")
        )
        self.assertEqual(set(selection["variants"]), {
            f"state_{index:02d}" for index in range(1, 14)
        })
        for variant, relative in selection["variants"].items():
            source = self.root / relative
            selected = (
                self.root
                / "selected-runs"
                / "repetition-01"
                / f"{variant}.json"
            )
            self.assertEqual(source.read_bytes(), selected.read_bytes())

        audit = json.loads(
            (self.root / "audit.json").read_text(encoding="utf-8")
        )
        projection_hashes = set()
        for directory in (
            "primary-run",
            "extended-timeout-retry",
            "state01-timeout-retry",
            "streamed-state01-retry",
        ):
            prefix = json.loads(
                (self.root / directory / "prefix.json").read_text(
                    encoding="utf-8"
                )
            )
            projection_hashes.add(task_prefix_sha256(prefix))
        control = json.loads(
            (
                repository_root()
                / "data"
                / "evidence"
                / "kubernetes-interaction-control-valid-20260730"
                / "prefix.json"
            ).read_text(encoding="utf-8")
        )
        projection_hashes.add(task_prefix_sha256(control))
        self.assertEqual(
            projection_hashes,
            {audit["task_prefix_projection_sha256"]},
        )

    def test_archive_manifest_is_byte_verified(self) -> None:
        audit = json.loads(
            (self.root / "audit.json").read_text(encoding="utf-8")
        )
        manifest_path = self.root / audit["file_manifest"]
        self.assertEqual(
            hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            audit["file_manifest_sha256"],
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["excluded_files"],
            [
                "README.md",
                "audit.json",
                "files.json",
            ],
        )
        for entry in manifest["files"]:
            path = self.root / entry["path"]
            self.assertEqual(path.stat().st_size, entry["bytes"])
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                entry["sha256"],
            )


if __name__ == "__main__":
    unittest.main()
