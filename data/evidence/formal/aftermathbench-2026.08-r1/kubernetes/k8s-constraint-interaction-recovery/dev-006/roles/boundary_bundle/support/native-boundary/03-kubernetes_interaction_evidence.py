from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from ..kubernetes_pairing import is_runtime_root_ca_configmap
from .kubernetes_api import KubernetesApi
from .kubernetes_interaction_prefix import NAMESPACE, SCENARIO_ID
from .kubernetes_interaction_recovery import KubernetesInteractionEnvironment

NORMALIZATION_CONTRACT = "kubernetes-interaction-boundary-v6"

# This task exposes Events as supporting diagnostics for workload transitions.
# Only Job Events carry failure evidence not already represented by an
# authoritative object. Deployment/ReplicaSet scaling messages and every Pod
# lifecycle observation are controller-runtime projections that are regenerated
# after restore and are neither scored nor used to derive a recovery scope.
_TASK_EVENT_SUBJECT_KINDS = frozenset({"Job"})

_DROP_KEYS = frozenset(
    {
        "resourceVersion",
        "managedFields",
        "selfLink",
        "creationTimestamp",
        "firstTimestamp",
        "lastTimestamp",
        "eventTime",
        "lastProbeTime",
        "lastTransitionTime",
        "lastUpdateTime",
        "startTime",
        "completionTime",
        "finishedAt",
        "startedAt",
        "first_received_at",
        "received_at",
        "containerID",
        "imageID",
        "podIP",
        "podIPs",
        "hostIP",
        "hostIPs",
    }
)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for original_key in sorted(value, key=str):
            key = str(original_key)
            if key in _DROP_KEYS:
                continue
            item = value[original_key]
            if key == "deletionTimestamp":
                result[key] = item is not None
            else:
                result[key] = _canonical_value(item)
        return result
    if isinstance(value, list):
        result = [_canonical_value(item) for item in value]
        if (
            result
            and all(
                isinstance(item, dict) and isinstance(item.get("type"), str)
                for item in result
            )
            and len({item["type"] for item in result}) == len(result)
        ):
            # Kubernetes condition arrays are semantic maps keyed by type;
            # controllers may rewrite their order without changing state.
            result.sort(key=lambda item: item["type"])
        return result
    return value


def canonical_kubernetes_object(document: dict[str, Any]) -> dict[str, Any]:
    """Keep native identities and authored state while dropping clock noise."""

    projected = _canonical_value(deepcopy(document))
    if projected.get("kind") == "Event":
        # Event object identity is an API-server allocation. The correlated
        # object's UID, reason, message and source are the diagnostic contract.
        projected["metadata"] = {
            "namespace": projected.get("metadata", {}).get("namespace")
        }
        projected.pop("count", None)
        projected.pop("series", None)
    return projected


def canonical_external_delivery(delivery: dict[str, Any]) -> dict[str, Any]:
    return _canonical_value(deepcopy(delivery))


def _object_key(document: dict[str, Any]) -> tuple[str, str, str, str]:
    metadata = document.get("metadata", {})
    return (
        str(document.get("kind", "")),
        str(metadata.get("namespace", "")),
        str(metadata.get("name", "")),
        str(metadata.get("uid", "")),
    )


def _event_key(document: dict[str, Any]) -> tuple[str, ...]:
    involved = document.get("involvedObject", {})
    return (
        str(document.get("type", "")),
        str(document.get("reason", "")),
        str(involved.get("kind", "")),
        str(involved.get("name", "")),
        str(involved.get("uid", "")),
        str(document.get("message", "")),
    )


def _is_decision_relevant_event(document: dict[str, Any]) -> bool:
    return (
        str(document.get("involvedObject", {}).get("kind", ""))
        in _TASK_EVENT_SUBJECT_KINDS
    )


def canonicalize_interaction_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    resource_groups = (
        "configmaps",
        "secrets",
        "serviceaccounts",
        "roles",
        "rolebindings",
        "deployments",
        "services",
        "jobs",
    )
    resources = [
        canonical_kubernetes_object(document)
        for group in resource_groups
        for document in snapshot.get(group, ())
        if not is_runtime_root_ca_configmap(document)
    ]
    resources.sort(key=_object_key)
    events = [
        canonical_kubernetes_object(document)
        for document in snapshot.get("events", ())
        if _is_decision_relevant_event(document)
    ]
    # Duplicate controller Events do not change a recovery decision. Preserve
    # one copy of each complete semantic observation while keeping the
    # correlated native object's UID.
    unique_events: dict[tuple[str, ...], dict[str, Any]] = {}
    for event in events:
        unique_events[_event_key(event)] = event
    external = [
        canonical_external_delivery(document)
        for document in snapshot.get("external_deliveries", ())
    ]
    external.sort(key=lambda item: str(item.get("key", "")))
    return {
        "namespace": NAMESPACE,
        "resources": resources,
        "events": [unique_events[key] for key in sorted(unique_events)],
        "external_deliveries": external,
        "boundary_facts": _canonical_value(
            deepcopy(snapshot.get("boundary_facts", {}))
        ),
        "protocol_violations": _canonical_value(
            deepcopy(snapshot.get("protocol_violations", []))
        ),
    }


def build_interaction_boundary_evidence(
    *,
    api: KubernetesApi,
    variant_id: str,
    external_url: str = "http://127.0.0.1:9092",
) -> dict[str, Any]:
    environment = KubernetesInteractionEnvironment(
        api,
        external_url=external_url,
    )
    state = canonicalize_interaction_snapshot(environment.snapshot())
    encoded = json.dumps(
        state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": "1.0",
        "normalization_contract": NORMALIZATION_CONTRACT,
        "scenario_id": SCENARIO_ID,
        "variant_id": variant_id,
        "state_sha256": hashlib.sha256(encoded).hexdigest(),
        "state": state,
    }


__all__ = [
    "NORMALIZATION_CONTRACT",
    "build_interaction_boundary_evidence",
    "canonical_external_delivery",
    "canonical_kubernetes_object",
    "canonicalize_interaction_snapshot",
]
