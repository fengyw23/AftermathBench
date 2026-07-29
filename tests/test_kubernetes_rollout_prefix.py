from __future__ import annotations

import unittest

from aftermath_bench.integrations.kubernetes_rollout_prefix import (
    NAMESPACE,
    _project_object,
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

    def test_service_projection_excludes_generated_cluster_ip(self) -> None:
        projected = _project_object(
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": "checkout-api",
                    "namespace": NAMESPACE,
                },
                "spec": {
                    "clusterIP": "10.96.1.25",
                    "clusterIPs": ["10.96.1.25"],
                    "selector": {"app": "checkout-api"},
                    "ports": [
                        {
                            "name": "app",
                            "port": 8080,
                            "protocol": "TCP",
                            "targetPort": 8080,
                        }
                    ],
                    "type": "ClusterIP",
                },
            }
        )
        self.assertNotIn("clusterIP", projected["spec"])
        self.assertEqual(
            projected["spec"]["selector"],
            {"app": "checkout-api"},
        )


if __name__ == "__main__":
    unittest.main()
