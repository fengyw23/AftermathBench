from __future__ import annotations

import copy
import unittest

from aftermath_bench.integrations.kubernetes_interaction_evidence import (
    canonical_external_delivery,
    canonical_kubernetes_object,
    canonicalize_interaction_snapshot,
)


class KubernetesInteractionEvidenceTests(unittest.TestCase):
    def test_object_projection_drops_clock_noise_but_keeps_uid(self) -> None:
        document = {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": "migration-1",
                "namespace": "aftermath-interactions",
                "uid": "uid-1",
                "resourceVersion": "10",
                "creationTimestamp": "2026-08-01T00:00:00Z",
                "labels": {"migration": "orders-platform-v2"},
            },
            "spec": {"suspend": False},
            "status": {
                "failed": 1,
                "completionTime": "2026-08-01T00:01:00Z",
            },
        }
        later = copy.deepcopy(document)
        later["metadata"]["resourceVersion"] = "900"
        later["metadata"]["creationTimestamp"] = "later"
        later["status"]["completionTime"] = "later"
        self.assertEqual(
            canonical_kubernetes_object(document),
            canonical_kubernetes_object(later),
        )
        later["metadata"]["uid"] = "uid-2"
        self.assertNotEqual(
            canonical_kubernetes_object(document),
            canonical_kubernetes_object(later),
        )

    def test_event_identity_noise_is_removed_but_subject_uid_is_kept(self) -> None:
        event = {
            "apiVersion": "v1",
            "kind": "Event",
            "metadata": {
                "name": "migration-1.abc",
                "namespace": "aftermath-interactions",
                "uid": "event-1",
                "creationTimestamp": "now",
            },
            "involvedObject": {
                "kind": "Job",
                "name": "migration-1",
                "uid": "job-uid-1",
            },
            "reason": "BackoffLimitExceeded",
            "message": "Job has reached the specified backoff limit",
            "type": "Warning",
            "count": 3,
            "lastTimestamp": "now",
        }
        replayed = copy.deepcopy(event)
        replayed["metadata"]["name"] = "migration-1.xyz"
        replayed["metadata"]["uid"] = "event-2"
        replayed["count"] = 9
        replayed["lastTimestamp"] = "later"
        self.assertEqual(
            canonical_kubernetes_object(event),
            canonical_kubernetes_object(replayed),
        )
        replayed["involvedObject"]["uid"] = "job-uid-2"
        self.assertNotEqual(
            canonical_kubernetes_object(event),
            canonical_kubernetes_object(replayed),
        )

    def test_external_projection_keeps_attempt_count_and_payload(self) -> None:
        delivery = {
            "key": "release:orders-platform-v1",
            "attempt_count": 1,
            "first_received_at": "now",
            "payload": {"version": "v1"},
            "attempts": [
                {
                    "id": 1,
                    "received_at": "now",
                    "payload": {"version": "v1"},
                }
            ],
        }
        replayed = copy.deepcopy(delivery)
        replayed["first_received_at"] = "later"
        replayed["attempts"][0]["received_at"] = "later"
        self.assertEqual(
            canonical_external_delivery(delivery),
            canonical_external_delivery(replayed),
        )
        replayed["attempt_count"] = 2
        self.assertNotEqual(
            canonical_external_delivery(delivery),
            canonical_external_delivery(replayed),
        )

    def test_duplicate_semantic_events_are_collapsed(self) -> None:
        event = {
            "apiVersion": "v1",
            "kind": "Event",
            "metadata": {
                "name": "event-a",
                "namespace": "aftermath-interactions",
                "uid": "event-a",
            },
            "involvedObject": {
                "kind": "Job",
                "name": "migration-1",
                "uid": "job-1",
            },
            "reason": "Failed",
            "message": "migration failed",
            "type": "Warning",
        }
        duplicate = copy.deepcopy(event)
        duplicate["metadata"]["name"] = "event-b"
        duplicate["metadata"]["uid"] = "event-b"
        state = canonicalize_interaction_snapshot(
            {
                "events": [event, duplicate],
                "external_deliveries": [],
                "boundary_facts": {},
            }
        )
        self.assertEqual(len(state["events"]), 1)

    def test_terminating_pods_are_not_part_of_the_stable_boundary(self) -> None:
        terminating = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "orders-api-v1-old",
                "namespace": "aftermath-interactions",
                "uid": "old-pod-uid",
                "deletionTimestamp": "2026-08-01T00:00:00Z",
            },
            "status": {"phase": "Running"},
        }
        active = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "orders-api-v2-current",
                "namespace": "aftermath-interactions",
                "uid": "current-pod-uid",
            },
            "status": {"phase": "Running"},
        }
        state = canonicalize_interaction_snapshot(
            {"pods": [terminating, active]}
        )
        self.assertEqual(
            [item["metadata"]["uid"] for item in state["resources"]],
            ["current-pod-uid"],
        )

    def test_ip_allocator_restart_event_is_not_boundary_evidence(self) -> None:
        repair = {
            "apiVersion": "v1",
            "kind": "Event",
            "metadata": {"namespace": "aftermath-interactions"},
            "involvedObject": {
                "kind": "Service",
                "name": "orders-api",
                "uid": "service-uid",
            },
            "reason": "ClusterIPNotAllocated",
            "reportingComponent": "ipallocator-repair-controller",
            "message": "Cluster IP is not allocated; repairing",
            "type": "Warning",
        }
        task_event = {
            "apiVersion": "v1",
            "kind": "Event",
            "metadata": {"namespace": "aftermath-interactions"},
            "involvedObject": {
                "kind": "Job",
                "name": "orders-schema-migration",
                "uid": "migration-uid",
            },
            "reason": "BackoffLimitExceeded",
            "reportingComponent": "job-controller",
            "message": "Job has reached the specified backoff limit",
            "type": "Warning",
        }
        state = canonicalize_interaction_snapshot(
            {"events": [repair, task_event]}
        )
        self.assertEqual(len(state["events"]), 1)
        self.assertEqual(state["events"][0]["reason"], "BackoffLimitExceeded")

    def test_pod_lifecycle_events_are_not_boundary_evidence(self) -> None:
        failed_mount = {
            "apiVersion": "v1",
            "kind": "Event",
            "metadata": {"namespace": "aftermath-interactions"},
            "involvedObject": {
                "kind": "Pod",
                "name": "orders-worker-v2-current",
                "uid": "worker-pod-uid",
            },
            "reason": "FailedMount",
            "reportingComponent": "kubelet",
            "message": "failed to sync configmap cache",
            "type": "Warning",
        }
        deployment_scale = {
            "apiVersion": "v1",
            "kind": "Event",
            "metadata": {"namespace": "aftermath-interactions"},
            "involvedObject": {
                "kind": "Deployment",
                "name": "orders-worker-v2",
                "uid": "worker-deployment-uid",
            },
            "reason": "ScalingReplicaSet",
            "reportingComponent": "deployment-controller",
            "message": "Scaled up replica set from 0 to 1",
            "type": "Normal",
        }
        state = canonicalize_interaction_snapshot(
            {"events": [failed_mount, deployment_scale]}
        )
        self.assertEqual(len(state["events"]), 1)
        self.assertEqual(state["events"][0]["reason"], "ScalingReplicaSet")


if __name__ == "__main__":
    unittest.main()
