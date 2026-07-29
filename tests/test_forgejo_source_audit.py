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
        self.assertTrue(
            all(
                len(item["sha256"]) == 64
                for item in audit["audited_paths"]
            )
        )


if __name__ == "__main__":
    unittest.main()
