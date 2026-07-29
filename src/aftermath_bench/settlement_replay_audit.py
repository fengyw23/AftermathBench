from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .integrations.kubernetes_settlement_faults import (
    KUBERNETES_SETTLEMENT_VARIANTS,
    SURFACE_ERROR,
)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_settlement_replay(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    boundaries = {
        variant: _read(root / f"{variant}.json")
        for variant in KUBERNETES_SETTLEMENT_VARIANTS
    }
    references = {
        variant: _read(root / f"{variant}-reference.json")
        for variant in KUBERNETES_SETTLEMENT_VARIANTS
    }
    prefix_hashes = {
        str(report["prefix_fingerprint"]) for report in boundaries.values()
    }
    mutation_counts = {
        variant: len(report.get("mutation_tools", []))
        for variant, report in references.items()
    }
    signatures = {
        tuple(report.get("mutation_tools", []))
        for report in references.values()
    }
    evidence_groups = {}
    for variant, report in references.items():
        queries = set(map(str, report.get("query_tools", [])))
        evidence_groups[variant] = {
            "native_objects": "list_objects" in queries,
            "events": "list_events" in queries,
            "job_receipt": "get_job_logs" in queries,
            "external_receiver": "list_external_deliveries" in queries,
        }
    checks = {
        "all_boundaries_pass": all(
            bool(report.get("passed")) for report in boundaries.values()
        ),
        "same_surface_error": all(
            report.get("surface_result") == SURFACE_ERROR
            for report in boundaries.values()
        ),
        "semantic_prefix_hash_stable": len(prefix_hashes) == 1,
        "all_references_pass": all(
            bool(report.get("evaluation", {}).get("passed"))
            and report.get("control_error") is None
            for report in references.values()
        ),
        "minimum_four_mutations": min(mutation_counts.values(), default=0) >= 4,
        "four_distinct_recovery_signatures": len(signatures) >= 4,
        "four_evidence_groups_used": all(
            all(groups.values()) for groups in evidence_groups.values()
        ),
        "four_downstream_repairs": all(
            int(report.get("downstream_repairs", 0)) >= 4
            for report in references.values()
        ),
    }
    return {
        "schema_version": "0.1",
        "scenario_id": "k8s-cronjob-settlement-dev-001",
        "source": "live native boundary and public-tool reference replay",
        "passed": all(checks.values()),
        "checks": checks,
        "observed": {
            "variant_count": len(boundaries),
            "prefix_hash_count": len(prefix_hashes),
            "mutation_counts": mutation_counts,
            "distinct_recovery_signature_count": len(signatures),
            "evidence_groups": evidence_groups,
        },
    }
