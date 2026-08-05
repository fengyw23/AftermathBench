from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .native_scenario import (
    load_native_scenario,
    validate_native_scenario_document,
)
from .runtime_gate import load_runtime_manifest, validate_runtime_manifest
from .schema import repository_root
from .strict_json import load_json_strict


DATASET_KIND = "researcher-designed-native-executed-synthetic"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_BLUEPRINT_IDENTITY_FIELDS = (
    "scenario_id",
    "domain_id",
    "instance_id",
    "family",
    "runtime_id",
    "title",
    "user_instruction",
    "fixture",
    "ambiguous_operation",
    "matched_variants",
    "instance_spec_sha256",
)


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _load_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = load_json_strict(path)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _blueprint_index(root: Path) -> tuple[dict[str, Path], tuple[str, ...]]:
    by_id: dict[str, Path] = {}
    duplicates: list[str] = []
    for path in sorted((root / "data" / "scenario_blueprints").glob("*/scenario.json")):
        payload = _load_object(path)
        scenario_id = str(payload.get("scenario_id", "")) if payload else ""
        if not scenario_id:
            continue
        if scenario_id in by_id:
            duplicates.append(scenario_id)
        else:
            by_id[scenario_id] = path
    return by_id, tuple(sorted(set(duplicates)))


def _runtime_index(root: Path) -> dict[str, tuple[Path, dict[str, Any], Any]]:
    result: dict[str, tuple[Path, dict[str, Any], Any]] = {}
    for path in sorted((root / "data" / "runtimes").glob("*/runtime.json")):
        payload = load_runtime_manifest(path)
        runtime_id = str(payload.get("runtime_id", ""))
        if runtime_id:
            result[runtime_id] = (path, payload, validate_runtime_manifest(payload))
    return result


def _variant_ids(payload: dict[str, Any] | None, collection: str) -> tuple[str, ...]:
    if not payload:
        return ()
    key = "variant" if collection in {"reports", "captures"} else "id"
    rows = payload.get(collection, ())
    if not isinstance(rows, list):
        return ()
    return tuple(
        str(row.get(key, ""))
        for row in rows
        if isinstance(row, dict) and row.get(key)
    )


def _path_list_declared(value: Any, root: Path) -> bool:
    return bool(
        isinstance(value, list)
        and value
        and all(
            isinstance(item, str)
            and item
            and (root / item).is_file()
            for item in value
        )
    )


def _provenance_checks(raw: dict[str, Any], root: Path) -> dict[str, bool]:
    provenance = raw.get("data_provenance")
    if not isinstance(provenance, dict):
        provenance = {}

    business = provenance.get("business_basis")
    business_declared = bool(
        isinstance(business, dict)
        and isinstance(business.get("kind"), str)
        and business.get("kind")
        and isinstance(business.get("rationale"), str)
        and business.get("rationale")
        and isinstance(business.get("references"), list)
    )

    authorship = provenance.get("authorship")
    authorship_declared = bool(
        isinstance(authorship, dict)
        and isinstance(authorship.get("researcher_authored"), list)
        and authorship.get("researcher_authored")
        and isinstance(authorship.get("native_generated"), list)
        and authorship.get("native_generated")
    )

    generator = provenance.get("generator")
    generator_declared = bool(
        isinstance(generator, dict)
        and _path_list_declared(generator.get("builder_paths"), root)
        and isinstance(generator.get("workflow_path"), str)
        and generator.get("workflow_path")
        and (root / generator["workflow_path"]).is_file()
    )

    generation_run = provenance.get("generation_run")
    generation_run_declared = bool(
        isinstance(generation_run, dict)
        and isinstance(generation_run.get("run_id"), int)
        and generation_run["run_id"] > 0
        and isinstance(generation_run.get("source_commit"), str)
        and _GIT_SHA.fullmatch(generation_run["source_commit"])
        and isinstance(generation_run.get("artifact_sha256"), str)
        and _SHA256.fullmatch(generation_run["artifact_sha256"])
    )

    return {
        "dataset_kind_declared": provenance.get("dataset_kind") == DATASET_KIND,
        "business_basis_declared": business_declared,
        "authorship_split_declared": authorship_declared,
        "benchmark_extensions_declared": isinstance(
            provenance.get("benchmark_authored_extensions"), list
        ),
        "parameter_sources_declared": bool(
            isinstance(provenance.get("parameter_sources"), list)
            and provenance.get("parameter_sources")
        ),
        "generator_paths_declared_and_present": generator_declared,
        "generation_run_bound": generation_run_declared,
    }


def _scenario_report(
    path: Path,
    *,
    root: Path,
    blueprints: dict[str, Path],
    runtimes: dict[str, tuple[Path, dict[str, Any], Any]],
) -> dict[str, Any]:
    scenario = load_native_scenario(path)
    raw = scenario.raw
    expected_variants = tuple(scenario.variants)
    expected_set = set(expected_variants)

    runtime_entry = runtimes.get(str(raw.get("runtime_id", "")))
    runtime_path: Path | None = None
    runtime_payload: dict[str, Any] = {}
    runtime_report = None
    if runtime_entry:
        runtime_path, runtime_payload, runtime_report = runtime_entry

    tool_manifest = runtime_payload.get("tool_provenance_manifest")
    tool_manifest_present = bool(
        isinstance(tool_manifest, str)
        and tool_manifest
        and (root / tool_manifest).is_file()
    )

    blueprint_path = blueprints.get(scenario.scenario_id)
    blueprint = _load_object(blueprint_path) if blueprint_path else None
    blueprint_identity_matches = bool(
        blueprint
        and all(
            field not in blueprint or blueprint.get(field) == raw.get(field)
            for field in _BLUEPRINT_IDENTITY_FIELDS
        )
    )

    artifacts = raw.get("admission_artifacts", {})
    artifact_paths: dict[str, Path] = {}
    artifact_payloads: dict[str, dict[str, Any] | None] = {}
    if isinstance(artifacts, dict):
        for key in sorted(artifacts):
            try:
                artifact_path = scenario.resolve_artifact(str(key))
            except (KeyError, OSError, ValueError):
                continue
            artifact_paths[str(key)] = artifact_path
            artifact_payloads[str(key)] = _load_object(artifact_path)

    required = {"prefix", "reference", "observed_graph", "baselines"}
    required_artifacts_present = all(
        key in artifact_paths and artifact_paths[key].is_file() for key in required
    )
    all_declared_artifacts_strict_json = bool(artifact_payloads) and all(
        payload is not None for payload in artifact_payloads.values()
    )
    artifact_identities_match = bool(artifact_payloads) and all(
        payload is not None
        and payload.get("scenario_id") == scenario.scenario_id
        for payload in artifact_payloads.values()
    )

    reference_variants = _variant_ids(artifact_payloads.get("reference"), "reports")
    replay_variants = _variant_ids(
        artifact_payloads.get("replay_evidence"), "captures"
    )
    reference_coverage = bool(reference_variants) and (
        len(reference_variants) == len(set(reference_variants))
        and set(reference_variants) == expected_set
    )
    replay_coverage = bool(replay_variants) and (
        len(replay_variants) == len(set(replay_variants))
        and set(replay_variants) == expected_set
    )
    admission = artifact_payloads.get("admission")
    admission_passed = bool(
        admission
        and admission.get("scenario_id") == scenario.scenario_id
        and admission.get("passed") is True
    )

    instance_hash = raw.get("instance_spec_sha256")
    instance_hash_valid = bool(
        isinstance(instance_hash, str) and _SHA256.fullmatch(instance_hash)
    )
    if instance_hash_valid:
        identity_bearing = [
            payload.get("instance_spec_sha256")
            for key, payload in artifact_payloads.items()
            if key in {"prefix", "reference", "replay_evidence"}
            and payload
            and "instance_spec_sha256" in payload
        ]
        instance_hash_consistent = bool(identity_bearing) and all(
            value == instance_hash for value in identity_bearing
        )
    else:
        instance_hash_consistent = False

    runtime_checks = {
        "runtime_manifest_present": runtime_entry is not None,
        "runtime_source_audit_passed": bool(
            runtime_report and runtime_report.source_audit_passed
        ),
        "runtime_execution_admitted": bool(
            runtime_report and runtime_report.execution_admitted
        ),
        "tool_provenance_manifest_present": tool_manifest_present,
    }
    native_checks = {
        "current_scenario_schema": raw.get("schema_version") == "1.0",
        "scenario_document_valid": not validate_native_scenario_document(scenario),
        "blueprint_present": blueprint_path is not None,
        "blueprint_identity_consistent": blueprint_identity_matches,
        "required_artifacts_present": required_artifacts_present,
        "all_declared_artifacts_strict_json": all_declared_artifacts_strict_json,
        "artifact_scenario_identities_match": artifact_identities_match,
        "reference_variants_complete": reference_coverage,
        "replay_variants_complete": replay_coverage,
        "admission_report_passed": admission_passed,
        "instance_spec_sha256_bound": instance_hash_valid,
        "instance_spec_sha256_propagated": instance_hash_consistent,
    }
    provenance_checks = _provenance_checks(raw, root)

    native_replay_chain_verified = all(runtime_checks.values()) and all(
        native_checks[name]
        for name in (
            "scenario_document_valid",
            "required_artifacts_present",
            "all_declared_artifacts_strict_json",
            "artifact_scenario_identities_match",
            "reference_variants_complete",
            "replay_variants_complete",
        )
    )
    semantic_provenance_complete = all(provenance_checks.values())
    publication_lineage_complete = bool(
        native_replay_chain_verified
        and native_checks["current_scenario_schema"]
        and native_checks["blueprint_present"]
        and native_checks["blueprint_identity_consistent"]
        and native_checks["admission_report_passed"]
        and native_checks["instance_spec_sha256_bound"]
        and native_checks["instance_spec_sha256_propagated"]
        and semantic_provenance_complete
    )

    caveats: list[str] = []
    if not native_replay_chain_verified:
        caveats.append("native_replay_chain_incomplete")
    if not all_declared_artifacts_strict_json:
        caveats.append("artifact_not_strict_json")
    if not provenance_checks["business_basis_declared"]:
        caveats.append("business_basis_undocumented")
    if not provenance_checks["authorship_split_declared"]:
        caveats.append("researcher_vs_native_authorship_undocumented")
    if not provenance_checks["generator_paths_declared_and_present"]:
        caveats.append("generator_not_bound_to_scenario")
    if not provenance_checks["generation_run_bound"]:
        caveats.append("generation_run_not_bound_to_scenario")
    if not provenance_checks["parameter_sources_declared"]:
        caveats.append("parameter_realism_undocumented")

    return {
        "scenario_id": scenario.scenario_id,
        "scenario_path": _relative(path, root),
        "domain_id": scenario.domain_id,
        "family_id": scenario.family_id,
        "instance_id": scenario.instance_id,
        "runtime_id": str(raw.get("runtime_id", "")),
        "benchmark_split": scenario.split,
        "benchmark_tier": scenario.tier,
        "variant_count": len(expected_variants),
        "blueprint_path": _relative(blueprint_path, root) if blueprint_path else None,
        "runtime_manifest_path": (
            _relative(runtime_path, root) if runtime_path else None
        ),
        "checks": {
            "runtime": runtime_checks,
            "native_generation": native_checks,
            "semantic_provenance": provenance_checks,
        },
        "native_replay_chain_verified": native_replay_chain_verified,
        "semantic_provenance_complete": semantic_provenance_complete,
        "publication_lineage_complete": publication_lineage_complete,
        "caveats": caveats,
    }


def build_data_lineage_audit(root: str | Path | None = None) -> dict[str, Any]:
    repo = Path(root).resolve() if root is not None else repository_root()
    blueprints, duplicate_blueprints = _blueprint_index(repo)
    runtimes = _runtime_index(repo)
    scenario_paths = tuple(
        sorted((repo / "data" / "scenarios").glob("*/scenario.json"))
    )
    scenarios = [
        _scenario_report(
            path,
            root=repo,
            blueprints=blueprints,
            runtimes=runtimes,
        )
        for path in scenario_paths
    ]

    def count_check(section: str, name: str) -> int:
        return sum(bool(row["checks"][section][name]) for row in scenarios)

    domains: dict[str, Counter[str]] = defaultdict(Counter)
    for row in scenarios:
        domain = domains[row["domain_id"]]
        domain["scenario_count"] += 1
        domain["variant_count"] += row["variant_count"]
        domain["native_replay_chain_verified"] += int(
            row["native_replay_chain_verified"]
        )
        domain["semantic_provenance_complete"] += int(
            row["semantic_provenance_complete"]
        )

    runtime_rows = []
    active_runtime_ids = sorted({row["runtime_id"] for row in scenarios})
    for runtime_id in active_runtime_ids:
        path, payload, report = runtimes[runtime_id]
        runtime_rows.append(
            {
                "runtime_id": runtime_id,
                "manifest_path": _relative(path, repo),
                "source_audit_passed": report.source_audit_passed,
                "execution_admitted": report.execution_admitted,
                "upstream_components": [
                    {
                        "repository": item.get("repository"),
                        "revision": item.get("revision"),
                        "license": item.get("license"),
                    }
                    for item in payload.get("upstream_components", ())
                ],
            }
        )

    summary = {
        "active_runtime_count": len(active_runtime_ids),
        "active_scenario_count": len(scenarios),
        "matched_state_count": sum(row["variant_count"] for row in scenarios),
        "current_schema_scenario_count": count_check(
            "native_generation", "current_scenario_schema"
        ),
        "blueprint_present_scenario_count": count_check(
            "native_generation", "blueprint_present"
        ),
        "native_replay_chain_verified_scenario_count": sum(
            row["native_replay_chain_verified"] for row in scenarios
        ),
        "hard_admission_report_scenario_count": count_check(
            "native_generation", "admission_report_passed"
        ),
        "instance_spec_bound_scenario_count": count_check(
            "native_generation", "instance_spec_sha256_bound"
        ),
        "business_basis_declared_scenario_count": count_check(
            "semantic_provenance", "business_basis_declared"
        ),
        "authorship_split_declared_scenario_count": count_check(
            "semantic_provenance", "authorship_split_declared"
        ),
        "generator_bound_scenario_count": count_check(
            "semantic_provenance", "generator_paths_declared_and_present"
        ),
        "generation_run_bound_scenario_count": count_check(
            "semantic_provenance", "generation_run_bound"
        ),
        "parameter_sources_declared_scenario_count": count_check(
            "semantic_provenance", "parameter_sources_declared"
        ),
        "semantic_provenance_complete_scenario_count": sum(
            row["semantic_provenance_complete"] for row in scenarios
        ),
        "publication_lineage_complete_scenario_count": sum(
            row["publication_lineage_complete"] for row in scenarios
        ),
    }

    native_count = summary["native_replay_chain_verified_scenario_count"]
    semantic_count = summary["semantic_provenance_complete_scenario_count"]
    overall = "complete" if semantic_count == len(scenarios) else "partial"
    return {
        "schema_version": "1.0",
        "audit_scope": "active public/development scenarios only; frozen hidden data is not read",
        "dataset_characterization": DATASET_KIND,
        "audit_completed": True,
        "publication_provenance_complete": overall == "complete",
        "reliability": {
            "native_runtime_and_replay": (
                "complete" if native_count == len(scenarios) else "strong_but_not_uniform"
            ),
            "scenario_semantic_provenance": (
                "complete" if semantic_count == len(scenarios) else "insufficient"
            ),
            "overall": overall,
        },
        "summary": summary,
        "duplicate_blueprint_scenario_ids": list(duplicate_blueprints),
        "domains": {key: dict(value) for key, value in sorted(domains.items())},
        "runtimes": runtime_rows,
        "scenarios": scenarios,
    }


__all__ = ["DATASET_KIND", "build_data_lineage_audit"]
