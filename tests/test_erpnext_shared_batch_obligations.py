from __future__ import annotations

import unittest
from unittest.mock import patch

from aftermath_bench.integrations.erpnext_shared_batch_obligations import (
    build_shared_batch_obligation_interactions,
)
from aftermath_bench.integrations.erpnext_shared_batch_probes import (
    SHARED_BATCH_INTERACTION_PROBES,
)
from aftermath_bench.integrations.erpnext_shared_batch_scope import (
    SHARED_BATCH_RECOVERY_SIGNATURES,
)


class SharedBatchObligationTests(unittest.TestCase):
    @patch(
        "aftermath_bench.integrations.erpnext_shared_batch_obligations."
        "_boundary_checks",
        return_value={
            "corrective_quantity_completed": False,
            "customer_reservation_preserved": True,
            "secondary_output_preserved": True,
        },
    )
    def test_native_probe_proves_repair_preservation_conflict(self, _checks) -> None:
        failures = {variant: {} for variant in SHARED_BATCH_RECOVERY_SIGNATURES}
        broken_check = {
            "repair_then_cancel_customer_reservation": (
                "customer_reservation_preserved"
            ),
            "repair_then_cancel_accepted_quality_inspection": (
                "secondary_output_preserved"
            ),
            "repair_then_cancel_unrelated_receipt": ("secondary_output_preserved"),
        }
        probes = {}
        for variant in SHARED_BATCH_RECOVERY_SIGNATURES:
            probes[variant] = []
            for action in SHARED_BATCH_INTERACTION_PROBES:
                checks = {
                    "corrective_quantity_completed": True,
                    "customer_reservation_preserved": True,
                    "secondary_output_preserved": True,
                }
                checks[broken_check[action]] = False
                probes[variant].append(
                    {
                        "action_id": action,
                        "tool_events": [
                            {
                                "tool": "cancel_document",
                                "arguments": {"doctype": "Native", "name": action},
                            }
                        ],
                        "result_state_sha256": "a" * 64,
                        "result_evaluation": {"checks": checks},
                    }
                )
        payload, audit = build_shared_batch_obligation_interactions(
            scenario_id="shared-test",
            prefix={},
            failures=failures,
            probes=probes,
        )
        self.assertEqual(payload["scenario_id"], "shared-test")
        self.assertTrue(audit.replay_bound)
        self.assertEqual(audit.gold_scope_count, 4)
        self.assertEqual(audit.probe_count, 12)
        self.assertEqual(audit.cross_obligation_witness_count, 12)
        self.assertEqual(audit.repair_preservation_conflict_count, 12)
        self.assertEqual(audit.conflicting_action_count, 3)
        self.assertEqual(audit.variants_with_repair_preservation_conflict, 4)


if __name__ == "__main__":
    unittest.main()
