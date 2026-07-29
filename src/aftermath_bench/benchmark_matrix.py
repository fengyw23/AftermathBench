from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BenchmarkMatrixReport:
    passed: bool
    checks: dict[str, bool]
    observed: dict[str, int]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, value in self.checks.items() if not value)


def load_benchmark_matrix(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_benchmark_matrix(raw: dict[str, Any]) -> BenchmarkMatrixReport:
    domains = tuple(raw.get("domains", ()))
    families = tuple(
        family
        for domain in domains
        for family in domain.get("families", ())
    )
    instances = tuple(
        instance
        for family in families
        for instance in family.get("instances", ())
    )
    states = tuple(raw.get("matched_error_states", ()))
    family_ids = [str(family.get("family_id", "")) for family in families]
    public_instances = [
        item for item in instances if item.get("split") == "public_dev"
    ]
    hidden_instances = [
        item for item in instances if item.get("split") == "hidden_test"
    ]
    checks = {
        "schema_version_present": bool(raw.get("schema_version")),
        "three_native_domains": len(domains) == 3,
        "four_families_per_domain": all(
            len(domain.get("families", ())) == 4 for domain in domains
        ),
        "family_ids_unique": len(family_ids) == len(set(family_ids)),
        "three_instances_per_family": all(
            len(family.get("instances", ())) == 3 for family in families
        ),
        "one_public_two_hidden_per_family": all(
            sum(
                instance.get("split") == "public_dev"
                for instance in family.get("instances", ())
            )
            == 1
            and sum(
                instance.get("split") == "hidden_test"
                for instance in family.get("instances", ())
            )
            == 2
            for family in families
        ),
        "four_matched_error_states": len(states) == 4,
        "every_family_names_a_real_error_operation": all(
            bool(family.get("error_operation")) for family in families
        ),
        "every_family_uses_native_entities": all(
            len(family.get("native_entities", ())) >= 5
            for family in families
        ),
        "two_independent_downstream_branches": all(
            len(set(map(str, family.get("independent_branches", ())))) >= 2
            for family in families
        ),
        "three_recovery_signatures_planned": all(
            len(family.get("required_recovery_signatures", ())) >= 3
            for family in families
        ),
        "protected_effects_declared": all(
            len(family.get("protected_effects", ())) >= 2
            for family in families
        ),
        "target_case_count_is_144": len(instances) * len(states) == 144,
    }
    return BenchmarkMatrixReport(
        passed=all(checks.values()),
        checks=checks,
        observed={
            "domain_count": len(domains),
            "family_count": len(families),
            "instance_count": len(instances),
            "matched_error_state_count": len(states),
            "public_instance_count": len(public_instances),
            "hidden_instance_count": len(hidden_instances),
            "target_case_count": len(instances) * len(states),
        },
    )
