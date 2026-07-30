from __future__ import annotations

import copy
import unittest

from aftermath_bench.integrations.forgejo_publication_recovery import (
    evaluate_forgejo_publication_recovery,
    relevant_release_deliveries,
)


def _prefix() -> dict:
    return {
        "pull_request_index": 2,
        "linked_issue_index": 1,
        "milestone_id": 1,
        "protected_pull_request_index": 3,
        "protected_issue_index": 4,
        "coordinator_hook_id": 7,
        "provenance_hook_id": 8,
        "base_branch": "release/2026.08",
        "release_tag": "v2026.08.0",
        "protected_release_tag": "v2026.07.3",
        "protected_asset_name": "prior.sha256",
        "expected_assets": [
            {"name": "binary.tgz", "sha256": "hash-a"},
            {"name": "binary.tgz.sha256", "sha256": "hash-b"},
            {"name": "binary.spdx.json", "sha256": "hash-c"},
        ],
    }


def _evidence() -> dict:
    return {
        "target_pull": {
            "state": "closed",
            "merged": True,
            "merge_base": "abc123",
        },
        "linked_issue": {"state": "closed"},
        "release_milestone": {"state": "closed"},
        "base_branch": {"commit": {"id": "abc123"}},
        "releases": [
            {
                "id": 20,
                "tag_name": "v2026.08.0",
                "target_commitish": "release/2026.08",
            },
            {
                "id": 19,
                "tag_name": "v2026.07.3",
                "target_commitish": "main",
            },
        ],
        "target_release_assets": [
            {"name": "binary.tgz", "content_sha256": "hash-a"},
            {
                "name": "binary.tgz.sha256",
                "content_sha256": "hash-b",
            },
            {
                "name": "binary.spdx.json",
                "content_sha256": "hash-c",
            },
        ],
        "protected_release_assets": [{"name": "prior.sha256"}],
        "protected_pull": {"state": "open", "merged": False},
        "protected_issue": {"state": "open"},
        "branch_protections": [{"rule_name": "release/*"}],
        "hooks": [
            {"id": 7, "active": True},
            {"id": 8, "active": True},
        ],
        "coordinator_history": [
            {"uuid": "delivery-a", "status": "succeeded"}
        ],
        "provenance_history": [
            {"uuid": "delivery-b", "status": "succeeded"}
        ],
        "external_deliveries": [
            {
                "key": "delivery-a",
                "attempt_count": 1,
                "payload": {"release": {"tag_name": "v2026.08.0"}},
            },
            {
                "key": "delivery-b",
                "attempt_count": 1,
                "payload": {"release": {"tag_name": "v2026.08.0"}},
            },
        ],
    }


class ForgejoPublicationEvaluationTest(unittest.TestCase):
    def test_complete_native_publication_passes(self) -> None:
        result = evaluate_forgejo_publication_recovery(
            _evidence(), prefix=_prefix()
        )
        self.assertTrue(result.passed, result.failures)
        self.assertTrue(result.components["repair_completeness"])

    def test_duplicate_receiver_attempt_is_protocol_failure(self) -> None:
        evidence = _evidence()
        evidence["external_deliveries"][0]["attempt_count"] = 2
        result = evaluate_forgejo_publication_recovery(
            evidence, prefix=_prefix()
        )
        self.assertFalse(result.passed)
        self.assertFalse(
            result.checks["coordinator_effect_applied_once"]
        )

    def test_missing_or_wrong_asset_is_goal_failure(self) -> None:
        evidence = _evidence()
        evidence["target_release_assets"][1]["content_sha256"] = "wrong"
        result = evaluate_forgejo_publication_recovery(
            evidence, prefix=_prefix()
        )
        self.assertFalse(result.passed)
        self.assertFalse(
            result.checks["all_asset_contents_match_approved_sources"]
        )

    def test_over_repair_of_prior_release_is_rejected(self) -> None:
        evidence = _evidence()
        evidence["protected_release_assets"] = []
        result = evaluate_forgejo_publication_recovery(
            evidence, prefix=_prefix()
        )
        self.assertFalse(result.passed)
        self.assertFalse(result.components["preservation"])

    def test_delivery_filter_uses_release_payload(self) -> None:
        records = copy.deepcopy(_evidence()["external_deliveries"])
        records.append(
            {
                "key": "other",
                "attempt_count": 1,
                "payload": {"release": {"tag_name": "v2026.09.0"}},
            }
        )
        self.assertEqual(
            [
                item["key"]
                for item in relevant_release_deliveries(
                    records, "v2026.08.0"
                )
            ],
            ["delivery-a", "delivery-b"],
        )


if __name__ == "__main__":
    unittest.main()
