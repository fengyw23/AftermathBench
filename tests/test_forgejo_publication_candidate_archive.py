from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


class ForgejoPublicationCandidateArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = (
            Path("data")
            / "evidence"
            / "forgejo-publication-candidate-control-20260731"
        )
        cls.result = json.loads(
            (cls.root / "result.json").read_text(encoding="utf-8")
        )
        cls.commitment = json.loads(
            (cls.root / "pre-model-commitment.json").read_text(
                encoding="utf-8"
            )
        )
        cls.run_metadata = json.loads(
            (cls.root / "run.json").read_text(encoding="utf-8")
        )

    def test_file_manifest_is_byte_verified(self) -> None:
        manifest = json.loads(
            (self.root / "files.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["excluded_files"], ["files.json"])
        self.assertEqual(manifest["file_count"], len(manifest["files"]))
        for entry in manifest["files"]:
            path = self.root / entry["path"]
            self.assertEqual(path.stat().st_size, entry["bytes"])
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                entry["sha256"],
            )

    def test_commitment_run_and_result_are_cross_bound(self) -> None:
        self.assertEqual(
            self.result["public_commitment_sha256"],
            self.commitment["public_commitment_sha256"],
        )
        self.assertEqual(
            self.result["source_commit"],
            self.run_metadata["head_sha"],
        )
        self.assertEqual(
            self.result["source_commit"],
            self.commitment["source_commit"],
        )
        self.assertEqual(self.run_metadata["conclusion"], "success")

    def test_public_aggregate_passes_preregistered_controls(self) -> None:
        self.assertEqual(
            self.result["admission"],
            {
                "passed": True,
                "admitted_tier": "hard",
                "failure_count": 0,
            },
        )
        self.assertEqual(
            self.result["reference"],
            {"case_count": 8, "pass_count": 8},
        )
        self.assertLessEqual(
            self.result["fixed_policies"]["maximum_pass_rate"],
            0.25,
        )
        self.assertEqual(
            self.result["fixed_policies"]["matched_group_solver_count"],
            0,
        )
        control = self.result["execution_control"]
        self.assertTrue(control["gate_pass"])
        self.assertEqual(control["completed_runs"], 8)
        self.assertEqual(control["run_error_count"], 0)
        self.assertEqual(control["task_pass_rate"], 1.0)
        self.assertEqual(self.result["usage_state"], "consumed")
        self.assertFalse(self.result["raw_hidden_bundle_published"])


if __name__ == "__main__":
    unittest.main()
