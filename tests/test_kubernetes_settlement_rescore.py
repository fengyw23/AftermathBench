from __future__ import annotations

import unittest
from pathlib import Path

from aftermath_bench.integrations.kubernetes_settlement_recovery import (
    evaluate_kubernetes_settlement_recovery,
)
from test_kubernetes_settlement_recovery import _passing_evidence


class KubernetesSettlementRescoreTest(unittest.TestCase):
    def test_visible_approved_receipt_is_the_current_gold(self) -> None:
        evaluation = evaluate_kubernetes_settlement_recovery(
            _passing_evidence()
        )
        self.assertTrue(evaluation.passed, evaluation.failures)

    def test_rescore_script_never_overwrites_raw_trajectory(self) -> None:
        # The executable is intentionally output-only; this test protects the
        # raw-evidence convention by checking its source for no write to input.
        source = (
            Path(__file__).parents[1]
            / "scripts"
            / "rescore_kubernetes_settlement_runs.py"
        ).read_text(encoding="utf-8")
        self.assertIn("--output", source)
        self.assertNotIn("path.write_text", source)


if __name__ == "__main__":
    unittest.main()
