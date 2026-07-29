from __future__ import annotations

import unittest

from aftermath_bench.integrations.kubernetes_faults import (
    KUBERNETES_FAULT_VARIANTS,
    SURFACE_ERROR,
    KubernetesRolloutFaultBoundary,
)


class FakeApi:
    def __init__(self):
        self.calls = []
        self.release = "v1"
        self.paused = False
        self.tainted = False

    def list(self, resource, **kwargs):
        self.calls.append(("list", resource, kwargs))
        if resource == "nodes":
            return [{"metadata": {"name": "node-1"}}]
        if resource == "replicasets" and self.release == "v2":
            return [
                {
                    "spec": {
                        "template": {
                            "metadata": {"labels": {"release": "v2"}}
                        }
                    },
                    "status": {"readyReplicas": 0 if self.tainted else 3},
                }
            ]
        return []

    def patch(self, resource, name, patch, **kwargs):
        self.calls.append(("patch", resource, name, patch, kwargs))
        if patch.get("spec", {}).get("paused") is True:
            self.paused = True
        labels = (
            patch.get("spec", {})
            .get("template", {})
            .get("metadata", {})
            .get("labels", {})
        )
        if labels.get("release") == "v2":
            self.release = "v2"
        return {}

    def taint_node(self, name, taint):
        self.calls.append(("taint_node", name, taint))
        self.tainted = True

    def wait_rollout(self, name, **kwargs):
        self.calls.append(("wait_rollout", name, kwargs))
        return "ready"


class KubernetesFaultBoundaryTests(unittest.TestCase):
    def test_all_variants_expose_the_same_connection_error(self):
        for variant in KUBERNETES_FAULT_VARIANTS:
            api = FakeApi()
            boundary = KubernetesRolloutFaultBoundary(api)
            with self.assertRaisesRegex(ConnectionError, SURFACE_ERROR):
                boundary.trigger(variant)

    def test_not_reached_performs_no_native_write(self):
        api = FakeApi()
        with self.assertRaises(ConnectionError):
            KubernetesRolloutFaultBoundary(api).trigger(
                "patch_request_not_reached"
            )
        self.assertEqual(api.calls, [])

    def test_paused_variant_commits_patch_without_replicaset(self):
        api = FakeApi()
        with self.assertRaises(ConnectionError):
            KubernetesRolloutFaultBoundary(api).trigger(
                "deployment_spec_committed_reconcile_paused"
            )
        self.assertTrue(api.paused)
        self.assertEqual(api.release, "v2")
        self.assertFalse(
            any(call[:2] == ("list", "replicasets") for call in api.calls)
        )

    def test_pending_variant_uses_a_native_node_taint(self):
        api = FakeApi()
        with self.assertRaises(ConnectionError):
            KubernetesRolloutFaultBoundary(api).trigger(
                "new_replicaset_created_rollout_pending"
            )
        self.assertTrue(api.tainted)
        self.assertEqual(api.release, "v2")
        self.assertTrue(
            any(call[:2] == ("list", "replicasets") for call in api.calls)
        )

    def test_unknown_variant_is_rejected_before_writes(self):
        api = FakeApi()
        with self.assertRaises(ValueError):
            KubernetesRolloutFaultBoundary(api).trigger("invented")
        self.assertEqual(api.calls, [])


if __name__ == "__main__":
    unittest.main()
