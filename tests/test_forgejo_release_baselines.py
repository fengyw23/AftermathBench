from __future__ import annotations

import unittest

from aftermath_bench.integrations.forgejo_release_baselines import (
    BASELINE_NAMES,
    run_fixed_forgejo_baseline,
)


class _Environment:
    prefix = {
        "pull_request_index": 2,
        "webhook_id": 7,
        "release_tag": "v1.2.3",
        "base_branch": "release/1.2",
    }

    def __init__(self, *, merged=True, external=False, failed=False):
        self.merged = merged
        self.external = external
        self.failed = failed
        self.calls = []

    def invoke(self, tool, **arguments):
        self.calls.append((tool, arguments))
        if tool == "get_pull_request":
            result = {"merged": self.merged}
        elif tool == "get_webhook_history":
            result = (
                [{"uuid": "failed-uuid", "status": "failed"}]
                if self.failed
                else []
            )
        elif tool == "list_external_deliveries":
            result = (
                [{"payload": {"pull_request": {"number": 2}}}]
                if self.external
                else []
            )
        elif tool == "list_releases":
            result = []
        else:
            result = {}
        return {"ok": True, "result": result}


class ForgejoReleaseBaselineTest(unittest.TestCase):
    def test_declares_compact_and_common_fixed_policies(self):
        self.assertIn("compact_state_tree", BASELINE_NAMES)
        self.assertIn("blind_retry", BASELINE_NAMES)
        self.assertIn("repair_failed_record_only", BASELINE_NAMES)

    def test_compact_tree_replays_only_failed_missing_effect(self):
        environment = _Environment(merged=True, external=False, failed=True)
        trace = run_fixed_forgejo_baseline(
            "compact_state_tree", environment=environment
        )
        mutations = [
            step["tool"]
            for step in trace
            if step["tool"] in {
                "merge_pull_request",
                "replay_webhook",
                "create_release",
            }
        ]
        self.assertEqual(mutations, ["replay_webhook", "create_release"])

    def test_compact_tree_preserves_already_applied_effect(self):
        environment = _Environment(merged=True, external=True, failed=True)
        trace = run_fixed_forgejo_baseline(
            "compact_state_tree", environment=environment
        )
        names = [step["tool"] for step in trace]
        self.assertNotIn("replay_webhook", names)
        self.assertIn("create_release", names)


if __name__ == "__main__":
    unittest.main()
