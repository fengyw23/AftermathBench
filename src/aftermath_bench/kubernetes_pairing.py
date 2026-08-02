from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any


def task_prefix_projection(prefix: Mapping[str, Any]) -> dict[str, Any]:
    """Return the task-semantic part of a native Kubernetes prefix.

    Every fresh kind cluster creates a different ``kube-root-ca.crt``
    ConfigMap. Its certificate bytes affect the raw runtime fingerprint but
    are not task evidence, a model-visible recovery requirement, or a mutable
    benchmark object. Excluding it lets paired runs prove equality of the
    authored task state without pretending two independent clusters share a
    control-plane identity.
    """

    projected = copy.deepcopy(dict(prefix))
    projected.pop("fingerprint", None)
    state = projected.get("state")
    if isinstance(state, dict):
        objects = state.get("objects")
        if isinstance(objects, list):
            state["objects"] = [
                item
                for item in objects
                if not is_runtime_root_ca_configmap(item)
            ]
    return projected


def task_prefix_sha256(prefix: Mapping[str, Any]) -> str:
    payload = json.dumps(
        task_prefix_projection(prefix),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def is_runtime_root_ca_configmap(item: Any) -> bool:
    if not isinstance(item, dict) or item.get("kind") != "ConfigMap":
        return False
    metadata = item.get("metadata")
    return (
        isinstance(metadata, dict)
        and metadata.get("name") == "kube-root-ca.crt"
    )


__all__ = [
    "is_runtime_root_ca_configmap",
    "task_prefix_projection",
    "task_prefix_sha256",
]
