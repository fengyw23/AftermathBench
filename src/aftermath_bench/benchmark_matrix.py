from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .strict_json import load_json_strict

FORMAL_SPLITS = frozenset({"public_dev", "hidden_test"})


@dataclass(frozen=True)
class ReleaseProfile:
    """Immutable release contract that a matrix cannot redefine."""

    target_release: str
    release_requirements: tuple[tuple[str, int], ...]
    families: tuple[tuple[str, str, str, int], ...]
    semantic_requirements: tuple[tuple[str, int, int], ...]
    target_case_count: int

    @property
    def domain_ids(self) -> frozenset[str]:
        return frozenset(domain_id for domain_id, _, _, _ in self.families)

    @property
    def family_contract(
        self,
    ) -> frozenset[tuple[str, str, int]]:
        return frozenset(
            (domain_id, family_id, variant_count)
            for domain_id, family_id, _, variant_count in self.families
        )

    @property
    def slot_contract(
        self,
    ) -> frozenset[tuple[str, str, str, str]]:
        slots: set[tuple[str, str, str, str]] = set()
        for domain_id, family_id, public_instance_id, _ in self.families:
            slots.update(
                {
                    (
                        domain_id,
                        family_id,
                        public_instance_id,
                        "public_dev",
                    ),
                    (domain_id, family_id, "test-001", "hidden_test"),
                    (domain_id, family_id, "test-002", "hidden_test"),
                }
            )
        return frozenset(slots)

    @property
    def requirements(self) -> dict[str, int]:
        return dict(self.release_requirements)

    @property
    def semantic_contract(self) -> frozenset[tuple[str, int, int]]:
        return frozenset(self.semantic_requirements)


TOP_CONFERENCE_FULL_PROFILE = ReleaseProfile(
    target_release="top-conference-full",
    release_requirements=(
        ("domain_count", 3),
        ("families_per_domain", 4),
        ("instances_per_family", 3),
        ("public_dev_per_family", 1),
        ("hidden_test_per_family", 2),
    ),
    families=(
        (
            "erpnext",
            "erpnext-partial-return-replacement-reconciliation",
            "dev-001",
            4,
        ),
        (
            "erpnext",
            "erpnext-sales-return-exchange-reconciliation",
            "dev-001",
            4,
        ),
        ("erpnext", "erpnext-manufacturing-rework", "dev-001", 4),
        ("erpnext", "erpnext-multiwarehouse-transfer", "dev-001", 4),
        (
            "forgejo",
            "forgejo-pr-merge-release-webhook",
            "dev-001",
            4,
        ),
        (
            "forgejo",
            "forgejo-release-package-publication",
            "dev-002",
            8,
        ),
        ("forgejo", "forgejo-package-provenance", "dev-001", 4),
        ("forgejo", "forgejo-migration-deployment", "dev-001", 4),
        ("kubernetes", "k8s-schema-rollout-recovery", "dev-003", 4),
        ("kubernetes", "k8s-settlement-orchestrated", "dev-002", 4),
        (
            "kubernetes",
            "k8s-constraint-interaction-recovery",
            "dev-005",
            13,
        ),
        (
            "kubernetes",
            "k8s-constraint-scope-recovery",
            "dev-004",
            4,
        ),
    ),
    semantic_requirements=(
        ("erpnext-partial-return-replacement-reconciliation", 3, 3),
        ("erpnext-sales-return-exchange-reconciliation", 3, 3),
        ("erpnext-manufacturing-rework", 3, 3),
        ("erpnext-multiwarehouse-transfer", 3, 3),
        ("forgejo-pr-merge-release-webhook", 3, 3),
        ("forgejo-release-package-publication", 3, 3),
        ("forgejo-package-provenance", 3, 3),
        ("forgejo-migration-deployment", 3, 3),
        ("k8s-schema-rollout-recovery", 3, 3),
        ("k8s-settlement-orchestrated", 3, 3),
        ("k8s-constraint-interaction-recovery", 8, 4),
        ("k8s-constraint-scope-recovery", 3, 3),
    ),
    target_case_count=183,
)

RELEASE_PROFILES = MappingProxyType(
    {
        TOP_CONFERENCE_FULL_PROFILE.target_release: (
            TOP_CONFERENCE_FULL_PROFILE
        )
    }
)


@dataclass(frozen=True)
class BenchmarkMatrixReport:
    passed: bool
    checks: dict[str, bool]
    observed: dict[str, int]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name, value in self.checks.items() if not value)


def load_benchmark_matrix(path: str | Path) -> dict[str, Any]:
    return load_json_strict(path)


def benchmark_family_index(
    raw: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(domain.get("domain_id", "")), str(family.get("family_id", ""))): family
        for domain in raw.get("domains", ())
        for family in domain.get("families", ())
    }


def benchmark_slots(raw: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    slots: list[dict[str, Any]] = []
    for domain in raw.get("domains", ()):
        domain_id = str(domain.get("domain_id", ""))
        for family in domain.get("families", ()):
            family_id = str(family.get("family_id", ""))
            variant_profile = dict(family.get("variant_profile", {}))
            for instance in family.get("instances", ()):
                instance_id = str(instance.get("id", ""))
                slots.append(
                    {
                        "slot_id": f"{domain_id}/{family_id}/{instance_id}",
                        "domain_id": domain_id,
                        "family_id": family_id,
                        "instance_id": instance_id,
                        "split": str(instance.get("split", "")),
                        "variant_profile": variant_profile,
                    }
                )
    return tuple(slots)


def validate_benchmark_matrix(raw: dict[str, Any]) -> BenchmarkMatrixReport:
    requirements = dict(raw.get("release_requirements", {}))
    target_release = str(raw.get("target_release", ""))
    release_profile = RELEASE_PROFILES.get(target_release)
    domains = tuple(raw.get("domains", ()))
    families = tuple(
        family for domain in domains for family in domain.get("families", ())
    )
    instances = tuple(
        instance
        for family in families
        for instance in family.get("instances", ())
    )
    slots = benchmark_slots(raw)
    taxonomy = tuple(raw.get("boundary_taxonomy", ()))

    domain_ids = [str(domain.get("domain_id", "")) for domain in domains]
    family_ids = [str(family.get("family_id", "")) for family in families]
    slot_ids = [str(slot["slot_id"]) for slot in slots]
    taxonomy_ids = [str(item.get("id", "")) for item in taxonomy]
    required_variant_counts = [
        int(family.get("variant_profile", {}).get("required_variant_count", 0))
        for family in families
    ]
    target_case_count = sum(
        int(slot["variant_profile"].get("required_variant_count", 0))
        for slot in slots
    )
    observed_family_contract = frozenset(
        (
            str(domain.get("domain_id", "")),
            str(family.get("family_id", "")),
            int(
                family.get("variant_profile", {}).get(
                    "required_variant_count", 0
                )
            ),
        )
        for domain in domains
        for family in domain.get("families", ())
    )
    observed_slot_contract = frozenset(
        (
            str(slot["domain_id"]),
            str(slot["family_id"]),
            str(slot["instance_id"]),
            str(slot["split"]),
        )
        for slot in slots
    )
    observed_semantic_contract = frozenset(
        (
            str(family.get("family_id", "")),
            int(
                family.get("variant_profile", {}).get(
                    "minimum_recovery_signatures", 0
                )
            ),
            int(
                family.get("variant_profile", {}).get(
                    "minimum_boundary_classes", 0
                )
            ),
        )
        for family in families
    )
    public_instances = [
        item for item in instances if item.get("split") == "public_dev"
    ]
    hidden_instances = [
        item for item in instances if item.get("split") == "hidden_test"
    ]

    domain_count = int(requirements.get("domain_count", 0))
    families_per_domain = int(requirements.get("families_per_domain", 0))
    instances_per_family = int(requirements.get("instances_per_family", 0))
    public_per_family = int(requirements.get("public_dev_per_family", 0))
    hidden_per_family = int(requirements.get("hidden_test_per_family", 0))

    checks = {
        "schema_version_is_2.0": raw.get("schema_version") == "2.0",
        "target_release_present": bool(raw.get("target_release")),
        "target_release_profile_known": release_profile is not None,
        "release_requirements_match_fixed_profile": bool(release_profile)
        and requirements == release_profile.requirements,
        "domain_ids_match_fixed_profile": bool(release_profile)
        and frozenset(domain_ids) == release_profile.domain_ids,
        "family_variant_contract_matches_fixed_profile": bool(
            release_profile
        )
        and observed_family_contract == release_profile.family_contract,
        "slot_contract_matches_fixed_profile": bool(release_profile)
        and observed_slot_contract == release_profile.slot_contract,
        "semantic_contract_matches_fixed_profile": bool(release_profile)
        and observed_semantic_contract == release_profile.semantic_contract,
        "target_case_count_matches_fixed_profile": bool(release_profile)
        and target_case_count == release_profile.target_case_count,
        "release_requirements_complete": all(
            value > 0
            for value in (
                domain_count,
                families_per_domain,
                instances_per_family,
                public_per_family,
                hidden_per_family,
            )
        ),
        "domain_count_matches_requirement": len(domains) == domain_count,
        "domain_ids_nonempty_and_unique": bool(domain_ids)
        and all(domain_ids)
        and len(domain_ids) == len(set(domain_ids)),
        "families_per_domain_match_requirement": bool(domains)
        and all(
            len(domain.get("families", ())) == families_per_domain
            for domain in domains
        ),
        "family_ids_nonempty_and_globally_unique": bool(family_ids)
        and all(family_ids)
        and len(family_ids) == len(set(family_ids)),
        "instances_per_family_match_requirement": bool(families)
        and all(
            len(family.get("instances", ())) == instances_per_family
            for family in families
        ),
        "instance_ids_unique_within_family": bool(families)
        and all(
            len(
                [
                    str(instance.get("id", ""))
                    for instance in family.get("instances", ())
                ]
            )
            == len(
                {
                    str(instance.get("id", ""))
                    for instance in family.get("instances", ())
                }
            )
            and all(
                str(instance.get("id", ""))
                for instance in family.get("instances", ())
            )
            for family in families
        ),
        "slot_ids_globally_unique": len(slot_ids) == len(set(slot_ids)),
        "formal_splits_only": all(
            str(instance.get("split", "")) in FORMAL_SPLITS
            for instance in instances
        ),
        "split_quota_matches_requirement": bool(families)
        and all(
            sum(
                instance.get("split") == "public_dev"
                for instance in family.get("instances", ())
            )
            == public_per_family
            and sum(
                instance.get("split") == "hidden_test"
                for instance in family.get("instances", ())
            )
            == hidden_per_family
            for family in families
        ),
        "boundary_taxonomy_ids_unique": len(taxonomy_ids) >= 4
        and all(taxonomy_ids)
        and len(taxonomy_ids) == len(set(taxonomy_ids)),
        "family_variant_profiles_are_explicit": bool(families)
        and all(count >= 4 for count in required_variant_counts)
        and all(
            3
            <= int(
                family.get("variant_profile", {}).get(
                    "minimum_recovery_signatures", 0
                )
            )
            <= len(
                set(
                    map(
                        str,
                        family.get("required_recovery_signatures", ()),
                    )
                )
            )
            and int(
                family.get("variant_profile", {}).get(
                    "minimum_boundary_classes", 0
                )
            )
            >= 3
            for family in families
        ),
        "every_family_names_a_real_error_operation": all(
            bool(family.get("error_operation")) for family in families
        ),
        "every_family_uses_native_entities": all(
            len(family.get("native_entities", ())) >= 5 for family in families
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
        "target_case_count_derived_from_family_profiles": target_case_count > 0,
    }
    return BenchmarkMatrixReport(
        passed=all(checks.values()),
        checks=checks,
        observed={
            "domain_count": len(domains),
            "family_count": len(families),
            "instance_count": len(instances),
            "boundary_taxonomy_count": len(taxonomy),
            "public_instance_count": len(public_instances),
            "hidden_instance_count": len(hidden_instances),
            "target_case_count": target_case_count,
        },
    )


__all__ = [
    "FORMAL_SPLITS",
    "RELEASE_PROFILES",
    "TOP_CONFERENCE_FULL_PROFILE",
    "BenchmarkMatrixReport",
    "ReleaseProfile",
    "benchmark_family_index",
    "benchmark_slots",
    "load_benchmark_matrix",
    "validate_benchmark_matrix",
]
