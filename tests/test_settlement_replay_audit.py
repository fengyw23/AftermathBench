from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.integrations.kubernetes_settlement_faults import (
    KUBERNETES_SETTLEMENT_VARIANTS,
    SURFACE_ERROR,
)
from aftermath_bench.settlement_replay_audit import audit_settlement_replay


class SettlementReplayAuditTest(unittest.TestCase):
    def _fixture(self, root: Path, *, stable_hash: bool) -> None:
        for index, variant in enumerate(KUBERNETES_SETTLEMENT_VARIANTS):
            (root / f"{variant}.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "surface_result": SURFACE_ERROR,
                        "prefix_fingerprint": (
                            "same" if stable_hash else f"hash-{index}"
                        ),
                    }
                ),
                encoding="utf-8",
            )
            (root / f"{variant}-reference.json").write_text(
                json.dumps(
                    {
                        "control_error": None,
                        "evaluation": {"passed": True},
                        "query_tools": [
                            "list_objects",
                            "list_events",
                            "get_job_logs",
                            "list_external_deliveries",
                        ],
                        "mutation_tools": [
                            f"branch-{index}",
                            "lease",
                            "delivery",
                            "ledger",
                        ],
                        "downstream_repairs": 4,
                    }
                ),
                encoding="utf-8",
            )

    def test_accepts_stable_prefix_and_four_replayed_signatures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root, stable_hash=True)
            report = audit_settlement_replay(root)
            self.assertTrue(report["passed"], report["checks"])
            self.assertEqual(
                report["observed"]["distinct_recovery_signature_count"], 4
            )

    def test_rejects_runtime_generated_prefix_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root, stable_hash=False)
            report = audit_settlement_replay(root)
            self.assertFalse(report["passed"])
            self.assertFalse(report["checks"]["semantic_prefix_hash_stable"])


if __name__ == "__main__":
    unittest.main()
