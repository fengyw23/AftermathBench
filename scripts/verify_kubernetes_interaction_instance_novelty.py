from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.kubernetes_interaction_instance import (
    DEFAULT_KUBERNETES_INTERACTION_INSTANCE,
    KubernetesInteractionInstanceSpec,
)

IDENTITY_FIELDS = (
    "scenario_id",
    "namespace",
    "application",
    "change_stem",
    "batch_id",
    "api_service",
    "current_api_deployment",
    "target_api_deployment",
    "current_worker_deployment",
    "target_worker_deployment",
    "current_credential",
    "next_credential",
    "backup_job",
    "migration_generate_name",
    "transition_job",
    "publication_job",
    "service_account",
    "observer_role",
    "schema_contract",
    "compatibility_contract",
    "credential_contract",
    "controller_contract",
    "publication_contract",
    "audit_contract",
    "database_catalog",
    "compatibility_bridge",
    "batch_state",
    "change_record",
    "release_ledger",
    "recovery_audit",
)

MINIMUM_SEMANTIC_FACT_CHANGES = 5
REUSE_SEAL_SCHEMA_VERSION = "1.0"
REUSE_SEAL_STAGE = "Kubernetes-initial-novelty-admission"


def tracked_paths(root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [
        root / item.decode("utf-8")
        for item in completed.stdout.split(b"\0")
        if item
    ]


def matching_tracked_paths(
    root: Path,
    instance: KubernetesInteractionInstanceSpec,
) -> list[Path]:
    arguments = ["git", "grep", "-I", "-l", "-F"]
    payload = instance.as_dict()
    for field in IDENTITY_FIELDS:
        arguments.extend(("-e", str(payload[field])))
    arguments.extend(("--", "."))
    completed = subprocess.run(
        arguments,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode not in {0, 1}:
        raise RuntimeError(
            "git grep failed during Kubernetes novelty scan: "
            f"{completed.stderr.strip()}"
        )
    return [root / line for line in completed.stdout.splitlines() if line]


def validate_bound_blueprint(
    instance: KubernetesInteractionInstanceSpec,
    path: Path,
) -> Path:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("bound blueprint must be a JSON object")
    if payload.get("scenario_id") != instance.scenario_id:
        raise ValueError("bound blueprint scenario_id does not match instance")
    if payload.get("instance_spec_sha256") != instance.sha256:
        raise ValueError(
            "bound blueprint instance_spec_sha256 does not match instance"
        )
    return path.resolve()


def novelty_scan_paths(
    paths: list[Path],
    *,
    instance_spec_path: Path,
    instance: KubernetesInteractionInstanceSpec,
    bound_blueprint_path: Path | None = None,
) -> list[Path]:
    excluded = {instance_spec_path.resolve()}
    if bound_blueprint_path is not None:
        excluded.add(validate_bound_blueprint(instance, bound_blueprint_path))
    return [path for path in paths if path.resolve() not in excluded]


def find_identity_overlaps(
    instance: KubernetesInteractionInstanceSpec,
    paths: list[Path],
) -> list[dict[str, str]]:
    corpus: list[tuple[Path, str]] = []
    for path in paths:
        try:
            corpus.append(
                (path, path.read_text(encoding="utf-8", errors="ignore"))
            )
        except OSError:
            continue
    overlaps: list[dict[str, str]] = []
    payload = instance.as_dict()
    for field in IDENTITY_FIELDS:
        value = str(payload[field])
        for path, text in corpus:
            if value in text:
                overlaps.append({"field": field, "path": path.as_posix()})
    return overlaps


def _repository_relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"path is outside the repository: {path}") from error


def _matching_paths_at_revision(
    root: Path,
    instance: KubernetesInteractionInstanceSpec,
    revision: str,
) -> list[str]:
    arguments = ["git", "grep", "-I", "-l", "-F"]
    payload = instance.as_dict()
    for field in IDENTITY_FIELDS:
        arguments.extend(("-e", str(payload[field])))
    arguments.extend((revision, "--", "."))
    completed = subprocess.run(
        arguments,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode not in {0, 1}:
        raise RuntimeError(
            "git grep failed during historical novelty scan: "
            f"{completed.stderr.strip()}"
        )
    paths: list[str] = []
    for line in completed.stdout.splitlines():
        prefix = f"{revision}:"
        if not line.startswith(prefix):
            raise ValueError(
                "historical novelty scan returned an unexpected path: "
                f"{line}"
            )
        paths.append(line[len(prefix) :])
    return paths


def _historical_identity_overlaps(
    root: Path,
    instance: KubernetesInteractionInstanceSpec,
    revision: str,
    paths: list[str],
) -> list[dict[str, str]]:
    corpus: list[tuple[str, str]] = []
    for path in paths:
        completed = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        corpus.append(
            (path, completed.stdout.decode("utf-8", errors="ignore"))
        )
    overlaps: list[dict[str, str]] = []
    payload = instance.as_dict()
    for field in IDENTITY_FIELDS:
        value = str(payload[field])
        for path, text in corpus:
            if value in text:
                overlaps.append(
                    {
                        "field": field,
                        "path": f"{revision}:{path}",
                    }
                )
    return overlaps


def validate_reuse_seal(
    path: Path,
    *,
    root: Path,
    instance: KubernetesInteractionInstanceSpec,
    instance_spec_path: Path,
    bound_blueprint_path: Path,
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("reuse seal must be a JSON object")
    expected_keys = {
        "schema_version",
        "stage",
        "source_commit",
        "source_run_id",
        "instance_spec_path",
        "bound_blueprint_path",
        "instance_spec_sha256",
        "derived_evidence_roots",
    }
    if set(payload) != expected_keys:
        raise ValueError("reuse seal has an unexpected field set")
    if (
        payload["schema_version"] != REUSE_SEAL_SCHEMA_VERSION
        or payload["stage"] != REUSE_SEAL_STAGE
        or not isinstance(payload["source_run_id"], int)
        or payload["source_run_id"] <= 0
        or payload["instance_spec_sha256"] != instance.sha256
    ):
        raise ValueError("reuse seal identity or source metadata is invalid")
    source_commit = payload["source_commit"]
    if not isinstance(source_commit, str) or re.fullmatch(
        r"[0-9a-f]{40}", source_commit
    ) is None:
        raise ValueError("reuse seal source_commit must be a full SHA-1")
    spec_relative = _repository_relative_path(root, instance_spec_path)
    blueprint_relative = _repository_relative_path(root, bound_blueprint_path)
    if (
        payload["instance_spec_path"] != spec_relative
        or payload["bound_blueprint_path"] != blueprint_relative
    ):
        raise ValueError("reuse seal does not bind the selected input paths")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", source_commit, "HEAD"],
        cwd=root,
        check=False,
    )
    if ancestor.returncode != 0:
        raise ValueError("reuse seal source_commit is not an ancestor of HEAD")
    unchanged = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            source_commit,
            "--",
            spec_relative,
            blueprint_relative,
        ],
        cwd=root,
        check=False,
    )
    if unchanged.returncode != 0:
        raise ValueError(
            "instance spec or bound blueprint changed after initial admission"
        )
    historical_candidates = _matching_paths_at_revision(
        root,
        instance,
        source_commit,
    )
    historical_scan = [
        candidate
        for candidate in historical_candidates
        if candidate not in {spec_relative, blueprint_relative}
    ]
    historical_overlaps = _historical_identity_overlaps(
        root,
        instance,
        source_commit,
        historical_scan,
    )
    if historical_overlaps:
        raise ValueError(
            "initial-admission commit already contained consumed identities"
        )
    roots = payload["derived_evidence_roots"]
    if not isinstance(roots, list) or not roots:
        raise ValueError("reuse seal must declare derived evidence roots")
    resolved_roots: list[Path] = []
    diagnostic_base = (root / "data/diagnostics/kubernetes").resolve()
    for raw in roots:
        if not isinstance(raw, str):
            raise TypeError(
                "derived evidence roots must stay under "
                "data/diagnostics/kubernetes"
            )
        resolved = (root / raw).resolve()
        _repository_relative_path(root, resolved)
        if (
            resolved == diagnostic_base
            or not resolved.is_relative_to(diagnostic_base)
        ):
            raise ValueError(
                "derived evidence roots must be specific descendants of "
                "data/diagnostics/kubernetes"
            )
        if not resolved.is_dir():
            raise ValueError(f"derived evidence root does not exist: {raw}")
        resolved_roots.append(resolved)
    return {
        "source_commit": source_commit,
        "source_run_id": payload["source_run_id"],
        "historical_identity_candidate_file_count": len(
            historical_candidates
        ),
        "historical_scanned_candidate_file_count": len(historical_scan),
        "derived_evidence_roots": [
            item.relative_to(root).as_posix() for item in resolved_roots
        ],
        "resolved_derived_evidence_roots": resolved_roots,
    }


def exclude_derived_evidence(
    paths: list[Path],
    roots: list[Path],
) -> list[Path]:
    return [
        path
        for path in paths
        if not any(path.resolve().is_relative_to(root) for root in roots)
    ]


def semantic_change_report(
    instance: KubernetesInteractionInstanceSpec,
    reference: KubernetesInteractionInstanceSpec = (
        DEFAULT_KUBERNETES_INTERACTION_INSTANCE
    ),
) -> dict[str, Any]:
    names = (
        "current_version",
        "target_version",
        "current_epoch",
        "target_epoch",
        "current_credential_generation",
        "target_credential_generation",
        "batch_id",
    )
    changed = [
        name
        for name in names
        if getattr(instance, name) != getattr(reference, name)
    ]
    return {
        "changed_fields": changed,
        "changed_field_count": len(changed),
        "minimum_required": MINIMUM_SEMANTIC_FACT_CHANGES,
        "passed": len(changed) >= MINIMUM_SEMANTIC_FACT_CHANGES,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reject a Kubernetes instance that reuses consumed identities "
            "or only renames the existing dev-005 facts."
        )
    )
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--bound-blueprint", type=Path)
    parser.add_argument(
        "--reuse-seal",
        type=Path,
        help=(
            "Bind a post-admission rerun to the unchanged first-admitted "
            "instance and exclude only its declared derived diagnostics."
        ),
    )
    args = parser.parse_args()
    root = args.repository_root.resolve()
    try:
        instance = KubernetesInteractionInstanceSpec.from_path(
            args.instance_spec
        )
        tracked = tracked_paths(root)
        matching = matching_tracked_paths(root, instance)
        scan_paths = novelty_scan_paths(
            matching,
            instance_spec_path=args.instance_spec,
            instance=instance,
            bound_blueprint_path=args.bound_blueprint,
        )
        reuse_proof = None
        if args.reuse_seal is not None:
            if args.bound_blueprint is None:
                raise ValueError("--reuse-seal requires --bound-blueprint")
            reuse_proof = validate_reuse_seal(
                args.reuse_seal,
                root=root,
                instance=instance,
                instance_spec_path=args.instance_spec,
                bound_blueprint_path=args.bound_blueprint,
            )
            scan_paths = exclude_derived_evidence(
                scan_paths,
                reuse_proof.pop("resolved_derived_evidence_roots"),
            )
        overlaps = find_identity_overlaps(instance, scan_paths)
        semantic = semantic_change_report(instance)
    except (OSError, TypeError, ValueError) as error:
        print(json.dumps({"passed": False, "error": str(error)}))
        return 2
    report = {
        "passed": not overlaps and bool(semantic["passed"]),
        "instance_spec_sha256": instance.sha256,
        "checked_identity_field_count": len(IDENTITY_FIELDS),
        "tracked_file_count": len(tracked),
        "identity_candidate_file_count": len(matching),
        "scanned_candidate_file_count": len(scan_paths),
        "identity_overlaps": overlaps,
        "semantic_change": semantic,
        "novelty_mode": "reuse" if reuse_proof is not None else "initial",
        "reuse_proof": reuse_proof,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
