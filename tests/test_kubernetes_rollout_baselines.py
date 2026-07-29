from __future__ import annotations

import unittest

from aftermath_bench.integrations.kubernetes_rollout_baselines import (
    BASELINE_NAMES,
    run_fixed_kubernetes_baseline,
)


class _Environment:
    def __init__(self, *, release="v2", paused=False, tainted=False):
        self.release = release
        self.paused = paused
        self.tainted = tainted
        self.calls = []

    def invoke(self, tool, **arguments):
        self.calls.append((tool, arguments))
        if tool == "get_object":
            return {
                "ok": True,
                "result": {
                    "spec": {
                        "paused": self.paused,
                        "template": {
                            "metadata": {
                                "labels": {"release": self.release}
                            }
                        },
                    }
                },
            }
        if tool == "list_objects" and arguments["resource"] == "nodes":
            taints = (
                [{"key": "aftermath.dev/rollout-pending"}]
                if self.tainted
                else []
            )
            return {
                "ok": True,
                "result": [
                    {"metadata": {"name": "worker"}, "spec": {"taints": taints}}
                ],
            }
        return {"ok": True, "result": {}}


class KubernetesRolloutBaselineTest(unittest.TestCase):
    def test_declares_expected_fixed_policies(self):
        self.assertIn("compact_boundary_tree", BASELINE_NAMES)
        self.assertIn("blind_retry", BASELINE_NAMES)
        self.assertIn("all_rollback", BASELINE_NAMES)

    def test_compact_tree_branches_on_paused_and_tainted_state(self):
        environment = _Environment(paused=True, tainted=True)
        trace = run_fixed_kubernetes_baseline(
            "compact_boundary_tree", environment=environment
        )
        mutations = [
            step
            for step in trace
            if step["tool"] in {"patch_object", "remove_node_taint"}
        ]
        self.assertEqual(
            mutations[0]["arguments"]["patch"],
            {"spec": {"paused": False}},
        )
        self.assertTrue(
            any(step["tool"] == "remove_node_taint" for step in mutations)
        )
        self.assertEqual(mutations[-1]["arguments"]["resource"], "service")

    def test_failed_record_only_never_completes_downstream(self):
        environment = _Environment(release="v1")
        trace = run_fixed_kubernetes_baseline(
            "repair_failed_record_only", environment=environment
        )
        patched = [
            step["arguments"].get("resource")
            for step in trace
            if step["tool"] == "patch_object"
        ]
        self.assertEqual(patched, ["deployment"])


if __name__ == "__main__":
    unittest.main()
