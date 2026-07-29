from __future__ import annotations

import unittest

from aftermath_bench.integrations.kubernetes_rollout_prefix import (
    NAMESPACE,
    prefix_fingerprint,
    prefix_manifests,
)


class KubernetesRolloutPrefixTest(unittest.TestCase):
    def test_prefix_contains_native_shared_and_protected_dependencies(self) -> None:
        manifests = prefix_manifests()
        kinds = [manifest["kind"] for manifest in manifests]
        self.assertGreaterEqual(len(manifests), 7)
        self.assertIn("Deployment", kinds)
        self.assertIn("Service", kinds)
        self.assertIn("HorizontalPodAutoscaler", kinds)
        self.assertIn("PodDisruptionBudget", kinds)
        self.assertTrue(
            all(
                manifest["metadata"].get("namespace", NAMESPACE) == NAMESPACE
                for manifest in manifests
            )
        )

    def test_prefix_fingerprint_is_key_order_invariant(self) -> None:
        left = {"namespace": NAMESPACE, "objects": [{"kind": "ConfigMap", "spec": None}]}
        right = {"objects": [{"spec": None, "kind": "ConfigMap"}], "namespace": NAMESPACE}
        self.assertEqual(prefix_fingerprint(left), prefix_fingerprint(right))

    def test_no_answer_style_repair_resource_is_seeded(self) -> None:
        rendered = str(prefix_manifests()).lower()
        self.assertNotIn("repair_", rendered)
        self.assertNotIn("recommended", rendered)


if __name__ == "__main__":
    unittest.main()
