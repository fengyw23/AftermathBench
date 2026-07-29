import unittest

from aftermath_bench.integrations.forgejo_recovery import (
    evaluate_forgejo_release_recovery,
    relevant_external_deliveries,
)


def _prefix():
    return {
        "pull_request_index": 2,
        "linked_issue_index": 1,
        "protected_pull_request_index": 3,
        "protected_issue_index": 4,
        "webhook_id": 7,
        "base_branch": "release/2026.07",
        "release_tag": "v2026.07.1",
        "protected_release_tag": "v2026.06.4",
    }


def _evidence():
    return {
        "target_pull": {
            "state": "closed",
            "merged": True,
            "merge_base": "abc123",
        },
        "linked_issue": {"state": "closed"},
        "base_branch": {"commit": {"id": "abc123"}},
        "releases": [
            {
                "tag_name": "v2026.07.1",
                "target_commitish": "release/2026.07",
            },
            {"tag_name": "v2026.06.4", "target_commitish": "main"},
        ],
        "protected_pull": {"state": "open", "merged": False},
        "protected_issue": {"state": "open"},
        "branch_protections": [{"rule_name": "release/*"}],
        "hooks": [{"id": 7, "active": True}],
        "webhook_history": [{"uuid": "delivery-a", "status": "succeeded"}],
        "external_deliveries": [
            {
                "key": "delivery-a",
                "attempt_count": 1,
                "payload": {"pull_request": {"number": 2}},
            }
        ],
    }


class ForgejoRecoveryEvaluatorTests(unittest.TestCase):
    def test_relevant_external_deliveries_filters_by_pull_payload(self):
        records = _evidence()["external_deliveries"] + [
            {
                "key": "other",
                "attempt_count": 1,
                "payload": {"pull_request": {"number": 3}},
            }
        ]
        self.assertEqual(
            [
                item["key"]
                for item in relevant_external_deliveries(records, 2)
            ],
            ["delivery-a"],
        )

    def test_accepts_complete_native_recovery(self):
        result = evaluate_forgejo_release_recovery(
            _evidence(), prefix=_prefix()
        )
        self.assertTrue(result.passed)
        self.assertEqual(
            result.components,
            {
                "goal_completion": True,
                "preservation": True,
                "protocol_safety": True,
            },
        )

    def test_separates_duplicate_attempt_from_effect(self):
        evidence = _evidence()
        evidence["external_deliveries"][0]["attempt_count"] = 2
        result = evaluate_forgejo_release_recovery(
            evidence, prefix=_prefix()
        )
        self.assertTrue(result.passed)
        self.assertEqual(
            result.diagnostics["target_external_attempt_count"], 2
        )

    def test_rejects_duplicate_effect_or_release(self):
        evidence = _evidence()
        evidence["external_deliveries"].append(
            {
                "key": "delivery-b",
                "attempt_count": 1,
                "payload": {"pull_request": {"number": 2}},
            }
        )
        evidence["releases"].append(
            {
                "tag_name": "v2026.07.1",
                "target_commitish": "release/2026.07",
            }
        )
        result = evaluate_forgejo_release_recovery(
            evidence, prefix=_prefix()
        )
        self.assertFalse(result.passed)
        self.assertFalse(
            result.checks["target_webhook_effect_applied_exactly_once"]
        )
        self.assertFalse(
            result.checks["target_release_published_once"]
        )

    def test_rejects_over_repair(self):
        evidence = _evidence()
        evidence["protected_pull"]["state"] = "closed"
        result = evaluate_forgejo_release_recovery(
            evidence, prefix=_prefix()
        )
        self.assertFalse(result.passed)
        self.assertFalse(result.components["preservation"])


if __name__ == "__main__":
    unittest.main()
