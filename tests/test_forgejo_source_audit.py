from __future__ import annotations

import json
import unittest

from aftermath_bench.schema import repository_root


class ForgejoSourceAuditTest(unittest.TestCase):
    def test_audit_is_pinned_and_does_not_claim_execution(self) -> None:
        audit = json.loads(
            (
                repository_root()
                / "data"
                / "runtimes"
                / "forgejo-main"
                / "source_audit.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            audit["revision"],
            "fbafae6c6288f3448aa6932576841f5daf5a9c76",
        )
        self.assertEqual(audit["license"], "GPL-3.0-or-later")
        self.assertEqual(
            audit["status"],
            "source-audited-execution-pending",
        )
        self.assertGreaterEqual(len(audit["audited_paths"]), 7)
        self.assertTrue(audit["verification"]["passed"])
        self.assertEqual(
            audit["verification"]["workflow_run_id"],
            30426124296,
        )
        self.assertTrue(
            all(
                len(item["sha256"]) == 64
                for item in audit["audited_paths"]
            )
        )

    def test_archived_ci_verification_matches_the_audit(self) -> None:
        root = (
            repository_root()
            / "data"
            / "runtimes"
            / "forgejo-main"
        )
        audit = json.loads(
            (root / "source_audit.json").read_text(encoding="utf-8")
        )
        verification = json.loads(
            (root / "source_verification.json").read_text(encoding="utf-8")
        )
        self.assertTrue(verification["source_verification"]["passed"])
        self.assertEqual(
            verification["source_verification"]["revision"],
            audit["revision"],
        )
        expected = {
            item["path"]: item["sha256"]
            for item in audit["audited_paths"]
        }
        self.assertEqual(
            verification["source_verification"]["actual_hashes"],
            expected,
        )
        self.assertTrue(
            verification["source_verification"]
            ["pinned_containerfile"]["all_digests_pinned"]
        )
        self.assertEqual(
            verification["image_build"]["built_from_verified_revision"],
            audit["revision"],
        )
        self.assertTrue(
            verification["image_build"]["image_id"].startswith("sha256:")
        )


if __name__ == "__main__":
    unittest.main()
