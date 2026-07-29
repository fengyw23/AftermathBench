from __future__ import annotations

import unittest

from aftermath_bench.integrations.kubernetes_settlement_baselines import (
    SETTLEMENT_BASELINES,
    run_kubernetes_settlement_baseline,
)


class _EmptyEnvironment:
    def event_log(self):
        return ()


class KubernetesSettlementBaselineTest(unittest.TestCase):
    def test_declares_common_and_compact_fixed_policies(self) -> None:
        self.assertEqual(
            set(SETTLEMENT_BASELINES),
            {
                "no_op",
                "blind_retry",
                "assume_committed",
                "repair_failed_record_only",
                "all_rollback",
                "deliver_immediately",
                "compact_state_tree",
            },
        )

    def test_no_op_performs_no_hidden_action(self) -> None:
        self.assertEqual(
            run_kubernetes_settlement_baseline(_EmptyEnvironment(), "no_op"),
            (),
        )

    def test_unknown_policy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_kubernetes_settlement_baseline(
                _EmptyEnvironment(), "oracle_in_disguise"
            )


if __name__ == "__main__":
    unittest.main()
