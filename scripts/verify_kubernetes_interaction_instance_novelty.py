from __future__ import annotations

import argparse
import json
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
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
