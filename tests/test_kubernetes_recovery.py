from __future__ import annotations

import unittest

from aftermath_bench.integrations.kubernetes_recovery import (
    evaluate_kubernetes_rollout_recovery,
)


def _deployment(name, release, replicas, ready):
    return {
        "metadata": {"name": name, "generation": 2},
        "spec": {
            "replicas": replicas,
            "template": {
                "metadata": {
                    "labels": {"release": release},
                    "annotations": {
                        "aftermath.dev/config-revision": release
                    },
                }
            },
        },
        "status": {
            "observedGeneration": 2,
            "readyReplicas": ready,
            "availableReplicas": ready,
        },
    }


def _evidence():
    ready_condition = [{"type": "Ready", "status": "True"}]
    return {
        "deployment": _deployment("checkout-api", "v2", 3, 3),
        "service": {
            "spec": {
                "selector": {
                    "app": "checkout-api",
                    "track": "stable",
                    "release": "v2",
                }
            }
        },
        "release_configmap": {
            "data": {
                "release": "v2",
                "changeTicket": "CHG-2026-1042",
            }
        },
        "horizontal_pod_autoscaler": {
            "spec": {
                "scaleTargetRef": {"name": "checkout-api"},
                "minReplicas": 3,
                "maxReplicas": 6,
            }
        },
        "pod_disruption_budget": {
            "spec": {
                "minAvailable": 2,
                "selector": {
                    "matchLabels": {
                        "app": "checkout-api",
                        "track": "stable",
                    }
                },
            }
        },
        "protected_deployment": _deployment(
            "billing-worker", "v7", 1, 1
        ),
        "replicasets": [
            {
                "spec": {
                    "template": {
                        "metadata": {"labels": {"release": "v1"}}
                    }
                }
            },
            {
                "spec": {
                    "template": {
                        "metadata": {"labels": {"release": "v2"}}
                    }
                }
            },
        ],
        "pods": [
            {
                "metadata": {"labels": {"release": "v2"}},
                "status": {"conditions": ready_condition},
            }
            for _ in range(3)
        ],
        "endpoint_slices": [
            {
                "endpoints": [
                    {"conditions": {"ready": True}} for _ in range(3)
                ]
            }
        ],
        "nodes": [{"metadata": {"name": "node-1"}, "spec": {}}],
        "protocol_violations": [],
    }


class KubernetesRecoveryEvaluatorTests(unittest.TestCase):
    def test_null_endpoint_list_is_a_goal_failure_not_a_crash(self):
        evidence = _evidence()
        evidence["endpoint_slices"] = [
            {
                "metadata": {"name": "checkout-api-empty"},
                "endpoints": None,
            }
        ]

        result = evaluate_kubernetes_rollout_recovery(evidence)

        self.assertFalse(result.passed)
        self.assertFalse(result.checks["service_has_three_ready_endpoints"])
        self.assertEqual(result.diagnostics["ready_endpoint_count"], 0)

    def test_accepts_converged_native_rollout(self):
        result = evaluate_kubernetes_rollout_recovery(_evidence())
        self.assertTrue(result.passed)
        self.assertEqual(result.diagnostics["ready_v2_pod_count"], 3)

    def test_rejects_traffic_switch_before_readiness(self):
        evidence = _evidence()
        evidence["deployment"]["status"]["readyReplicas"] = 2
        evidence["pods"][2]["status"]["conditions"][0]["status"] = "False"
        result = evaluate_kubernetes_rollout_recovery(evidence)
        self.assertFalse(result.passed)
        self.assertFalse(
            result.checks["deployment_has_three_ready_replicas"]
        )
        self.assertFalse(result.checks["three_v2_pods_ready"])

    def test_rejects_over_repair_of_shared_policy(self):
        evidence = _evidence()
        evidence["horizontal_pod_autoscaler"]["spec"]["minReplicas"] = 1
        result = evaluate_kubernetes_rollout_recovery(evidence)
        self.assertFalse(result.passed)
        self.assertFalse(result.components["preservation"])

    def test_rejects_residual_native_blocker(self):
        evidence = _evidence()
        evidence["nodes"][0]["spec"]["taints"] = [
            {
                "key": "aftermath.dev/rollout-pending",
                "effect": "NoSchedule",
            }
        ]
        result = evaluate_kubernetes_rollout_recovery(evidence)
        self.assertFalse(result.passed)
        self.assertFalse(result.checks["rollout_taint_removed"])

    def test_rejects_transient_traffic_switch_before_readiness(self):
        evidence = _evidence()
        evidence["protocol_violations"] = [
            {
                "type": "service_switch_before_v2_ready",
                "deployment_release": "v2",
                "ready_replicas": 1,
            }
        ]
        result = evaluate_kubernetes_rollout_recovery(evidence)
        self.assertFalse(result.passed)
        self.assertFalse(
            result.checks["no_traffic_switch_before_v2_ready"]
        )


if __name__ == "__main__":
    unittest.main()
