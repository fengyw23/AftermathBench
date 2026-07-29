from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from .kubernetes_api import KubernetesApi


NAMESPACE = "aftermath-rollout"
PRIMARY_DEPLOYMENT = "checkout-api"
PROTECTED_DEPLOYMENT = "billing-worker"


def prefix_manifests() -> tuple[dict[str, Any], ...]:
    labels = {"app": PRIMARY_DEPLOYMENT, "track": "stable"}
    return (
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": NAMESPACE},
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "checkout-release", "namespace": NAMESPACE},
            "data": {
                "release": "v1",
                "requiredReadyReplicas": "3",
                "changeTicket": "CHG-2026-1042",
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "checkout-api", "namespace": NAMESPACE},
            "spec": {
                "selector": labels,
                "ports": [{"name": "app", "port": 8080, "targetPort": 8080}],
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": PRIMARY_DEPLOYMENT, "namespace": NAMESPACE},
            "spec": {
                "replicas": 3,
                "revisionHistoryLimit": 4,
                "strategy": {
                    "type": "RollingUpdate",
                    "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 1},
                },
                "selector": {"matchLabels": labels},
                "template": {
                    "metadata": {
                        "labels": {**labels, "release": "v1"},
                        "annotations": {
                            "aftermath.dev/config-revision": "v1",
                            "aftermath.dev/change-ticket": "CHG-2026-1042",
                        },
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": "checkout",
                                "image": "registry.k8s.io/pause:3.10",
                                "resources": {
                                    "requests": {"cpu": "10m", "memory": "8Mi"}
                                },
                            }
                        ]
                    },
                },
            },
        },
        {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {"name": PRIMARY_DEPLOYMENT, "namespace": NAMESPACE},
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": PRIMARY_DEPLOYMENT,
                },
                "minReplicas": 3,
                "maxReplicas": 6,
                "metrics": [
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "cpu",
                            "target": {
                                "type": "Utilization",
                                "averageUtilization": 60,
                            },
                        },
                    }
                ],
            },
        },
        {
            "apiVersion": "policy/v1",
            "kind": "PodDisruptionBudget",
            "metadata": {"name": PRIMARY_DEPLOYMENT, "namespace": NAMESPACE},
            "spec": {
                "minAvailable": 2,
                "selector": {"matchLabels": labels},
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": PROTECTED_DEPLOYMENT, "namespace": NAMESPACE},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": PROTECTED_DEPLOYMENT}},
                "template": {
                    "metadata": {
                        "labels": {
                            "app": PROTECTED_DEPLOYMENT,
                            "release": "v7",
                        }
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": "billing",
                                "image": "registry.k8s.io/pause:3.10",
                                "resources": {
                                    "requests": {"cpu": "10m", "memory": "8Mi"}
                                },
                            }
                        ]
                    },
                },
            },
        },
    )


def reset_prefix(api: KubernetesApi) -> dict[str, Any]:
    deletion = api.delete("namespace", NAMESPACE)
    if deletion:
        api.wait_deleted("namespace", NAMESPACE)
    writes = [api.apply(manifest) for manifest in prefix_manifests()]
    api.wait_rollout(PRIMARY_DEPLOYMENT, namespace=NAMESPACE)
    api.wait_rollout(PROTECTED_DEPLOYMENT, namespace=NAMESPACE)
    state = capture_prefix(api)
    return {
        "successful_writes": len(writes),
        "state": state,
        "fingerprint": prefix_fingerprint(state),
    }


def _project_object(document: dict[str, Any]) -> dict[str, Any]:
    metadata = document["metadata"]
    return {
        "apiVersion": document["apiVersion"],
        "kind": document["kind"],
        "metadata": {
            "name": metadata["name"],
            "namespace": metadata.get("namespace"),
            "labels": metadata.get("labels", {}),
            "annotations": metadata.get("annotations", {}),
        },
        "spec": document.get("spec"),
        "data": document.get("data"),
    }


def capture_prefix(api: KubernetesApi) -> dict[str, Any]:
    objects = (
        api.get("configmap", "checkout-release", namespace=NAMESPACE),
        api.get("service", "checkout-api", namespace=NAMESPACE),
        api.get("deployment", PRIMARY_DEPLOYMENT, namespace=NAMESPACE),
        api.get(
            "horizontalpodautoscaler",
            PRIMARY_DEPLOYMENT,
            namespace=NAMESPACE,
        ),
        api.get(
            "poddisruptionbudget",
            PRIMARY_DEPLOYMENT,
            namespace=NAMESPACE,
        ),
        api.get("deployment", PROTECTED_DEPLOYMENT, namespace=NAMESPACE),
    )
    return {
        "namespace": NAMESPACE,
        "objects": [_project_object(document) for document in objects],
    }


def prefix_fingerprint(state: dict[str, Any]) -> str:
    canonical = json.dumps(
        state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def mutate_prefix(api: KubernetesApi) -> dict[str, Any]:
    deployment = api.patch(
        "deployment",
        PRIMARY_DEPLOYMENT,
        {
            "spec": {
                "template": {
                    "metadata": {
                        "labels": {"release": "v2"},
                        "annotations": {
                            "aftermath.dev/config-revision": "v2"
                        },
                    }
                }
            }
        },
        namespace=NAMESPACE,
    )
    service = api.patch(
        "service",
        "checkout-api",
        {"spec": {"selector": {"app": PRIMARY_DEPLOYMENT, "track": "canary"}}},
        namespace=NAMESPACE,
    )
    config = api.patch(
        "configmap",
        "checkout-release",
        {"data": {"release": "v2"}},
        namespace=NAMESPACE,
    )
    return {
        "deployment_generation": deployment["metadata"].get("generation"),
        "service_selector": service["spec"]["selector"],
        "config_release": config["data"]["release"],
    }
