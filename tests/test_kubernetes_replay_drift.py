from __future__ import annotations

import unittest

from aftermath_bench.kubernetes_replay_drift import (
    compare_kubernetes_replay_states,
)


def _resource(*, name: str, uid: str, replicas: int) -> dict:
    return {
        "kind": "Deployment",
        "metadata": {"namespace": "task", "name": name, "uid": uid},
        "spec": {"replicas": replicas},
    }


class KubernetesReplayDriftTests(unittest.TestCase):
    def test_matches_equivalent_resource_order(self) -> None:
        left = {
            "state_sha256": "left",
            "state": {
                "namespace": "task",
                "resources": [
                    _resource(name="api", uid="a", replicas=1),
                    _resource(name="worker", uid="b", replicas=1),
                ],
            },
        }
        right = {
            "state_sha256": "right",
            "state": {
                "namespace": "task",
                "resources": list(reversed(left["state"]["resources"])),
            },
        }
        result = compare_kubernetes_replay_states(left, right)
        self.assertTrue(result["matches"])
        self.assertEqual(result["differences"], [])

    def test_identifies_one_native_object_field(self) -> None:
        left = {
            "state_sha256": "left",
            "state": {
                "namespace": "task",
                "resources": [_resource(name="api", uid="a", replicas=1)],
            },
        }
        right = {
            "state_sha256": "right",
            "state": {
                "namespace": "task",
                "resources": [_resource(name="api", uid="a", replicas=0)],
            },
        }
        result = compare_kubernetes_replay_states(left, right)
        self.assertFalse(result["matches"])
        self.assertEqual(result["difference_count_capped"], 1)
        self.assertIn("/spec/replicas", result["differences"][0]["path"])

    def test_redacts_secret_data_values(self) -> None:
        left = {
            "state": {
                "resources": [
                    {
                        "kind": "Secret",
                        "metadata": {
                            "namespace": "task",
                            "name": "credential",
                            "uid": "s",
                        },
                        "data": {"password": "left-value"},
                    }
                ]
            }
        }
        right = {
            "state": {
                "resources": [
                    {
                        "kind": "Secret",
                        "metadata": {
                            "namespace": "task",
                            "name": "credential",
                            "uid": "s",
                        },
                        "data": {"password": "right-value"},
                    }
                ]
            }
        }
        result = compare_kubernetes_replay_states(left, right)
        difference = result["differences"][0]
        self.assertNotIn("left-value", str(difference))
        self.assertNotIn("right-value", str(difference))
        self.assertIn("redacted_sha256", difference["expected"])


if __name__ == "__main__":
    unittest.main()
