from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_value(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        lowered = path.lower()
        if any(part in lowered for part in ("/data/", "token", "password", "secret")):
            return {"redacted_sha256": _digest(value)}
        return value if len(value) <= 160 else value[:157] + "..."
    return {"sha256": _digest(value), "type": type(value).__name__}


def _resource_key(value: Mapping[str, Any]) -> str:
    metadata = value.get("metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    return "/".join(
        str(item)
        for item in (
            value.get("kind", ""),
            metadata.get("namespace", ""),
            metadata.get("name", ""),
            metadata.get("uid", ""),
        )
    )


def _event_key(value: Mapping[str, Any]) -> str:
    involved = value.get("involvedObject", {})
    if not isinstance(involved, Mapping):
        involved = {}
    identity = (
        value.get("type", ""),
        value.get("reason", ""),
        involved.get("kind", ""),
        involved.get("name", ""),
        involved.get("uid", ""),
        value.get("message", ""),
    )
    return _digest(identity)


def _external_key(value: Mapping[str, Any]) -> str:
    return str(value.get("key", ""))


def _index(
    values: Any,
    *,
    key,
) -> dict[str, Any]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return {"<invalid-sequence>": values}
    result: dict[str, Any] = {}
    for index, item in enumerate(values):
        if not isinstance(item, Mapping):
            result[f"<invalid-{index}>"] = item
            continue
        identity = key(item)
        if identity in result:
            identity = f"{identity}#duplicate-{index}"
        result[identity] = dict(item)
    return result


def _comparison_shape(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "namespace": state.get("namespace"),
        "resources": _index(state.get("resources", []), key=_resource_key),
        "events": _index(state.get("events", []), key=_event_key),
        "external_deliveries": _index(
            state.get("external_deliveries", []), key=_external_key
        ),
        "boundary_facts": state.get("boundary_facts", {}),
        "protocol_violations": state.get("protocol_violations", []),
    }


def _diff(
    expected: Any,
    actual: Any,
    *,
    path: str,
    output: list[dict[str, Any]],
    maximum: int,
) -> None:
    if len(output) >= maximum:
        return
    if type(expected) is not type(actual):
        output.append(
            {
                "path": path,
                "kind": "type_changed",
                "expected": _safe_value(expected, path=path),
                "actual": _safe_value(actual, path=path),
            }
        )
        return
    if isinstance(expected, Mapping):
        expected_keys = set(expected)
        actual_keys = set(actual)
        for key in sorted(expected_keys - actual_keys, key=str):
            child = f"{path}/{key}"
            output.append(
                {
                    "path": child,
                    "kind": "missing",
                    "expected": _safe_value(expected[key], path=child),
                }
            )
            if len(output) >= maximum:
                return
        for key in sorted(actual_keys - expected_keys, key=str):
            child = f"{path}/{key}"
            output.append(
                {
                    "path": child,
                    "kind": "unexpected",
                    "actual": _safe_value(actual[key], path=child),
                }
            )
            if len(output) >= maximum:
                return
        for key in sorted(expected_keys & actual_keys, key=str):
            _diff(
                expected[key],
                actual[key],
                path=f"{path}/{key}",
                output=output,
                maximum=maximum,
            )
            if len(output) >= maximum:
                return
        return
    if isinstance(expected, list):
        if len(expected) != len(actual):
            output.append(
                {
                    "path": path,
                    "kind": "length_changed",
                    "expected": len(expected),
                    "actual": len(actual),
                }
            )
            if len(output) >= maximum:
                return
        for index, (left, right) in enumerate(zip(expected, actual, strict=False)):
            _diff(
                left,
                right,
                path=f"{path}/{index}",
                output=output,
                maximum=maximum,
            )
            if len(output) >= maximum:
                return
        return
    if expected != actual:
        output.append(
            {
                "path": path,
                "kind": "value_changed",
                "expected": _safe_value(expected, path=path),
                "actual": _safe_value(actual, path=path),
            }
        )


def compare_kubernetes_replay_states(
    expected_evidence: Mapping[str, Any],
    actual_evidence: Mapping[str, Any],
    *,
    maximum_differences: int = 500,
) -> dict[str, Any]:
    if maximum_differences <= 0:
        raise ValueError("maximum_differences must be positive")
    expected_state = expected_evidence.get("state")
    actual_state = actual_evidence.get("state")
    if not isinstance(expected_state, Mapping) or not isinstance(
        actual_state, Mapping
    ):
        raise TypeError("both evidence objects must contain state objects")
    expected = _comparison_shape(expected_state)
    actual = _comparison_shape(actual_state)
    differences: list[dict[str, Any]] = []
    _diff(
        expected,
        actual,
        path="",
        output=differences,
        maximum=maximum_differences,
    )
    return {
        "schema_version": "1.0",
        "expected_state_sha256": expected_evidence.get("state_sha256"),
        "actual_state_sha256": actual_evidence.get("state_sha256"),
        "matches": not differences,
        "difference_count_capped": len(differences),
        "difference_limit": maximum_differences,
        "differences": differences,
    }


__all__ = ["compare_kubernetes_replay_states"]
