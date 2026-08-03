from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .erpnext_manufacturing_state_evidence import (
    manufacturing_boundary_projection,
)
from .erpnext_sales_return_state_evidence import (
    canonical_state_fingerprint,
)


BoundaryProjection = Callable[[dict[str, Any]], dict[str, Any]]


TRUSTED_BOUNDARY_PROJECTIONS: dict[str, BoundaryProjection] = {
    "erpnext-manufacturing-rework": manufacturing_boundary_projection,
}


def native_boundaries_equivalent(
    family_id: str,
    boundary: dict[str, Any],
    replay: dict[str, Any],
) -> bool:
    """Return whether two exact captures bind the same recovery boundary.

    Exact equality is the default for every family.  A family may opt into a
    trusted projection only when the native runtime has recovery-irrelevant
    audit state whose observation can race with snapshot capture.  Even then,
    both full states retain independently verified exact fingerprints and all
    non-state source bindings must remain identical.
    """

    if boundary == replay:
        return True
    projection = TRUSTED_BOUNDARY_PROJECTIONS.get(family_id)
    if projection is None:
        return False
    for payload in (boundary, replay):
        state = payload.get("state")
        if (
            not isinstance(state, dict)
            or payload.get("state_fingerprint")
            != canonical_state_fingerprint(state)
        ):
            return False
        semantic = payload.get("failure_state_semantic_fingerprint")
        if (
            not isinstance(semantic, str)
            or semantic
            != canonical_state_fingerprint(projection(state))
        ):
            return False
    ignored = {"state", "state_fingerprint"}
    boundary_bindings = {
        key: value for key, value in boundary.items() if key not in ignored
    }
    replay_bindings = {
        key: value for key, value in replay.items() if key not in ignored
    }
    return (
        boundary_bindings == replay_bindings
        and projection(boundary["state"]) == projection(replay["state"])
    )


__all__ = [
    "TRUSTED_BOUNDARY_PROJECTIONS",
    "native_boundaries_equivalent",
]
