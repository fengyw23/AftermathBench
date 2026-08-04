from __future__ import annotations

import unittest

from aftermath_bench.obligation_interaction_audit import (
    analyze_obligation_interactions,
)


def _probe(action: str, after: dict[str, bool]) -> dict[str, object]:
    return {
        "action_id": action,
        "tool_events": [{"tool": "mutate_native_record", "arguments": {"id": action}}],
        "result_state_sha256": "a" * 64,
        "result_evaluation": after,
    }


class ObligationInteractionAuditTest(unittest.TestCase):
    def _payload(self) -> dict[str, object]:
        obligations = [
            {"id": "failed_goal", "protected": False},
            {"id": "shared_payment", "protected": True},
            {"id": "valid_inventory", "protected": True},
            {"id": "external_once", "protected": True},
        ]
        boundary = {
            "failed_goal": False,
            "shared_payment": True,
            "valid_inventory": True,
            "external_once": True,
        }
        safe = {
            "failed_goal": True,
            "shared_payment": True,
            "valid_inventory": True,
            "external_once": True,
        }
        unsafe = {
            "failed_goal": True,
            "shared_payment": False,
            "valid_inventory": False,
            "external_once": True,
        }
        return {
            "obligations": obligations,
            "actions": [{"id": "local"}, {"id": "rollback_shared"}],
            "rows": [
                {
                    "variant": "request_absent",
                    "boundary_evaluation": boundary,
                    "gold_action_ids": ["local"],
                    "probes": [
                        _probe("local", safe),
                        _probe("rollback_shared", unsafe),
                    ],
                },
                {
                    "variant": "request_committed",
                    "boundary_evaluation": boundary,
                    "gold_action_ids": ["rollback_shared"],
                    "probes": [
                        _probe("local", safe),
                        _probe("rollback_shared", unsafe),
                    ],
                },
            ],
        }

    def test_derives_cross_obligation_conflicts_from_evaluator_deltas(self) -> None:
        audit = analyze_obligation_interactions(self._payload())
        self.assertEqual(audit.variant_count, 2)
        self.assertEqual(audit.gold_scope_count, 2)
        self.assertEqual(audit.protected_obligation_count, 3)
        self.assertEqual(audit.cross_obligation_witness_count, 2)
        self.assertEqual(audit.repair_preservation_conflict_count, 2)
        self.assertEqual(audit.conflicting_action_count, 1)
        self.assertEqual(audit.variants_with_repair_preservation_conflict, 2)
        self.assertTrue(audit.replay_bound)

    def test_rejects_incomplete_obligation_evaluation(self) -> None:
        payload = self._payload()
        del payload["rows"][0]["boundary_evaluation"]["external_once"]  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "every declared obligation"):
            analyze_obligation_interactions(payload)

    def test_marks_unbound_probe_without_native_state_hash(self) -> None:
        payload = self._payload()
        payload["rows"][0]["probes"][0]["result_state_sha256"] = "draft"  # type: ignore[index]
        audit = analyze_obligation_interactions(payload)
        self.assertFalse(audit.replay_bound)


if __name__ == "__main__":
    unittest.main()
