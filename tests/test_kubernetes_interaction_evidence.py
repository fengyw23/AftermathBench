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

    def test_pods_are_not_persistent_boundary_authority(self) -> None:
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
        self.assertEqual(state["resources"], [])

    def test_runtime_root_ca_is_not_task_boundary_evidence(self) -> None:
        runtime_projection = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "kube-root-ca.crt",
                "namespace": "aftermath-interactions",
                "uid": "cluster-specific-uid",
            },
            "data": {"ca.crt": "cluster-specific-certificate"},
        }
        authored = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "schema-contract",
                "namespace": "aftermath-interactions",
                "uid": "persistent-uid",
            },
            "data": {"epoch": "2"},
        }
        state = canonicalize_interaction_snapshot(
            {"configmaps": [runtime_projection, authored]}
        )
        self.assertEqual(len(state["resources"]), 1)
        self.assertEqual(
            state["resources"][0]["metadata"]["name"],
            "schema-contract",
        )

    def test_kubernetes_condition_order_is_semantically_normalized(self) -> None:
        document = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "worker",
                "namespace": "aftermath-interactions",
                "uid": "worker-uid",
            },
            "status": {
                "conditions": [
                    {"type": "Progressing", "status": "True"},
                    {"type": "Available", "status": "True"},
                ]
            },
        }
        reordered = copy.deepcopy(document)
        reordered["status"]["conditions"].reverse()
        self.assertEqual(
            canonical_kubernetes_object(document),
            canonical_kubernetes_object(reordered),
        )

    def test_two_consumers_match_despite_controller_runtime_reprojection(
        self,
    ) -> None:
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "worker",
                "namespace": "aftermath-interactions",
                "uid": "persistent-deployment-uid",
            },
            "spec": {"replicas": 1},
            "status": {
                "conditions": [
                    {"type": "Progressing", "status": "True"},
                    {"type": "Available", "status": "True"},
                ],
                "readyReplicas": 1,
            },
        }
        job_event = {
            "kind": "Event",
            "metadata": {"namespace": "aftermath-interactions"},
            "involvedObject": {
                "kind": "Job",
                "name": "migration",
                "uid": "persistent-job-uid",
            },
            "reason": "Complete",
            "message": "Job completed",
            "type": "Normal",
        }
        original = {
            "deployments": [deployment],
            "pods": [
                {
                    "kind": "Pod",
                    "metadata": {"name": "worker-old", "uid": "pod-old"},
                }
            ],
            "events": [job_event],
            "boundary_facts": {"scope": "preserve"},
        }
        replayed = copy.deepcopy(original)
        replayed["deployments"][0]["status"]["conditions"].reverse()
        replayed["pods"] = [
            {
                "kind": "Pod",
                "metadata": {"name": "worker-new", "uid": "pod-new"},
            }
        ]
        replayed["events"].append(
            {
                "kind": "Event",
                "metadata": {"namespace": "aftermath-interactions"},
                "involvedObject": {
                    "kind": "ReplicaSet",
                    "name": "worker-rs",
                    "uid": "persistent-rs-uid",
                },
                "reason": "SuccessfulCreate",
                "message": "Created pod: worker-new",
                "type": "Normal",
            }
        )
        self.assertEqual(
            canonicalize_interaction_snapshot(original),
            canonicalize_interaction_snapshot(replayed),
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

    def test_pod_and_deployment_events_are_not_boundary_evidence(self) -> None:
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
        self.assertEqual(state["events"], [])

    def test_endpoint_controller_conflicts_are_not_boundary_evidence(self) -> None:
        endpoint_conflict = {
            "apiVersion": "v1",
            "kind": "Event",
            "metadata": {"namespace": "aftermath-interactions"},
            "involvedObject": {
                "kind": "Endpoints",
                "name": "orders-api",
                "uid": "endpoints-uid",
            },
            "reason": "FailedToUpdateEndpoint",
            "reportingComponent": "endpoint-controller",
            "message": "the object has been modified",
            "type": "Warning",
        }
        state = canonicalize_interaction_snapshot(
            {"events": [endpoint_conflict]}
        )
        self.assertEqual(state["events"], [])


if __name__ == "__main__":
    unittest.main()
