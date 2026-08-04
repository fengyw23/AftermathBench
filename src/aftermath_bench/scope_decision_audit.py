from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from itertools import combinations
from typing import Any


@dataclass(frozen=True)
class ScopeDecisionAudit:
    variant_count: int
    recovery_signature_count: int
    observable_surface_count: int
    minimum_static_certificate_size: int | None
    optimal_adaptive_worst_case_depth: int | None
    single_surface_solvers: tuple[str, ...]
    indistinguishable_variant_pairs: tuple[tuple[str, str], ...]

    @property
    def identifiable(self) -> bool:
        return not self.indistinguishable_variant_pairs


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def analyze_scope_decision_matrix(payload: dict[str, Any]) -> ScopeDecisionAudit:
    """Measure how many observable facts are needed to choose a recovery scope.

    Each row must contain a variant id, its gold recovery signature, and a
    complete mapping from public query surface ids to canonical observations.
    Unlike reference-trace query depth, this computes over all matched variants
    and therefore detects a task whose apparently large graph is solved by one
    discriminating query.
    """

    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list) or len(raw_rows) < 2:
        raise ValueError("scope decision matrix requires at least two rows")

    rows: list[tuple[str, str, dict[str, str]]] = []
    variants: set[str] = set()
    expected_surfaces: set[str] | None = None
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, dict):
            raise TypeError(f"scope decision row {index} is not an object")
        variant = str(raw.get("variant", "")).strip()
        signature = str(raw.get("recovery_signature", "")).strip()
        observations = raw.get("observations")
        if not variant or not signature or not isinstance(observations, dict):
            raise ValueError(f"scope decision row {index} is incomplete")
        if variant in variants:
            raise ValueError(f"duplicate scope decision variant: {variant}")
        variants.add(variant)
        surfaces = {str(key) for key in observations}
        if expected_surfaces is None:
            expected_surfaces = surfaces
        elif surfaces != expected_surfaces:
            raise ValueError("every scope decision row must cover the same surfaces")
        rows.append(
            (
                variant,
                signature,
                {str(key): _canonical(value) for key, value in observations.items()},
            )
        )

    observations = tuple(sorted(expected_surfaces or ()))
    if not observations:
        raise ValueError("scope decision matrix has no observable surfaces")
    raw_requirements = payload.get("surface_requirements")
    if raw_requirements is None:
        requirements = {surface: (surface,) for surface in observations}
    else:
        if not isinstance(raw_requirements, dict) or set(raw_requirements) != set(
            observations
        ):
            raise ValueError(
                "surface_requirements must cover every observation exactly once"
            )
        requirements: dict[str, tuple[str, ...]] = {}
        for observation in observations:
            raw = raw_requirements[observation]
            if not isinstance(raw, list) or not raw or any(
                not isinstance(item, str) or not item.strip() for item in raw
            ):
                raise ValueError(
                    f"invalid query-surface requirements for {observation!r}"
                )
            requirements[observation] = tuple(sorted(set(raw)))
    query_surfaces = tuple(
        sorted({surface for values in requirements.values() for surface in values})
    )
    signatures = tuple(row[1] for row in rows)
    if len(set(signatures)) < 2:
        raise ValueError("scope decision matrix requires multiple recovery signatures")

    indistinguishable: list[tuple[str, str]] = []
    different_scope_pairs: list[tuple[int, int]] = []
    for left, right in combinations(range(len(rows)), 2):
        if signatures[left] == signatures[right]:
            continue
        different_scope_pairs.append((left, right))
        if all(
            rows[left][2][observation] == rows[right][2][observation]
            for observation in observations
        ):
            indistinguishable.append((rows[left][0], rows[right][0]))

    def unlocked(selected: frozenset[str]) -> tuple[str, ...]:
        return tuple(
            observation
            for observation in observations
            if set(requirements[observation]).issubset(selected)
        )

    def fingerprint(index: int, selected: frozenset[str]) -> tuple[str, ...]:
        return tuple(rows[index][2][item] for item in unlocked(selected))

    minimum_certificate: int | None = None
    if not indistinguishable:
        for size in range(1, len(query_surfaces) + 1):
            if any(
                all(
                    fingerprint(left, frozenset(selected))
                    != fingerprint(right, frozenset(selected))
                    for left, right in different_scope_pairs
                )
                for selected in combinations(query_surfaces, size)
            ):
                minimum_certificate = size
                break

    def homogeneous(indices: tuple[int, ...]) -> bool:
        return len({signatures[index] for index in indices}) <= 1

    @cache
    def decision_depth(
        indices: tuple[int, ...],
        selected: frozenset[str],
        remaining: tuple[str, ...],
    ) -> int | None:
        if homogeneous(indices):
            return 0
        best: int | None = None
        for surface in remaining:
            partitions: dict[str, list[int]] = {}
            next_selected = selected | {surface}
            for index in indices:
                key = _canonical(fingerprint(index, next_selected))
                partitions.setdefault(key, []).append(index)
            next_remaining = tuple(item for item in remaining if item != surface)
            child_depths = [
                decision_depth(tuple(group), next_selected, next_remaining)
                for group in partitions.values()
            ]
            if any(depth is None for depth in child_depths):
                continue
            candidate = 1 + max(int(depth) for depth in child_depths)
            best = candidate if best is None else min(best, candidate)
        return best

    all_indices = tuple(range(len(rows)))
    adaptive_depth = decision_depth(all_indices, frozenset(), query_surfaces)
    single_surface_solvers = tuple(
        surface
        for surface in query_surfaces
        if all(
            homogeneous(tuple(group))
            for group in _partitions_by_fingerprint(
                rows, all_indices, frozenset({surface}), fingerprint
            ).values()
        )
    )
    return ScopeDecisionAudit(
        variant_count=len(rows),
        recovery_signature_count=len(set(signatures)),
        observable_surface_count=len(query_surfaces),
        minimum_static_certificate_size=minimum_certificate,
        optimal_adaptive_worst_case_depth=adaptive_depth,
        single_surface_solvers=single_surface_solvers,
        indistinguishable_variant_pairs=tuple(indistinguishable),
    )


def _partitions(
    rows: list[tuple[str, str, dict[str, str]]],
    indices: tuple[int, ...],
    surface: str,
) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for index in indices:
        result.setdefault(rows[index][2][surface], []).append(index)
    return result


def _partitions_by_fingerprint(
    rows: list[tuple[str, str, dict[str, str]]],
    indices: tuple[int, ...],
    selected: frozenset[str],
    fingerprint,
) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for index in indices:
        result.setdefault(_canonical(fingerprint(index, selected)), []).append(index)
    return result
