from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class FrozenBundle:
    private_attestation: dict[str, Any]
    public_commitment: dict[str, Any]


def verify_frozen_bundle(
    *,
    bundle_root: Path,
    private_attestation_path: Path,
    public_commitment_path: Path,
    allowed_unbound_relative_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """Recompute every frozen input and its salted public commitment."""

    root = bundle_root.resolve()
    private_path = private_attestation_path.resolve()
    public_path = public_commitment_path.resolve()
    for path in (private_path, public_path):
        path.relative_to(root)
    private = json.loads(private_path.read_text(encoding="utf-8"))
    public = json.loads(public_path.read_text(encoding="utf-8"))
    allowed = {
        private_path.relative_to(root).as_posix(),
        public_path.relative_to(root).as_posix(),
        *(Path(value).as_posix() for value in allowed_unbound_relative_paths),
    }
    declared_files = {
        str(item["path"]): item
        for item in private.get("files", [])
    }
    failures = []
    for relative, item in declared_files.items():
        path = root / relative
        if not path.is_file():
            failures.append(f"missing:{relative}")
            continue
        if path.stat().st_size != int(item["bytes"]):
            failures.append(f"bytes:{relative}")
        if file_sha256(path) != str(item["sha256"]):
            failures.append(f"sha256:{relative}")
    observed_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    undeclared = sorted(observed_files - set(declared_files) - allowed)
    failures.extend(f"undeclared:{path}" for path in undeclared)
    manifest = {
        key: private[key]
        for key in (
            "schema_version",
            "scenario_id",
            "source_commit",
            "runtime_revision",
            "scenario_sha256",
            "instance_spec_semantic_sha256",
            "files",
        )
    }
    root_sha = hashlib.sha256(_canonical(manifest)).hexdigest()
    if root_sha != str(private.get("bundle_root_sha256", "")):
        failures.append("bundle_root_sha256")
    commitment = hashlib.sha256(
        (
            f"{private.get('commitment_salt', '')}:"
            f"{private.get('bundle_root_sha256', '')}"
        ).encode("utf-8")
    ).hexdigest()
    if commitment != str(private.get("public_commitment_sha256", "")):
        failures.append("private_public_commitment")
    if commitment != str(public.get("public_commitment_sha256", "")):
        failures.append("public_commitment")
    for key in (
        "scenario_id",
        "source_commit",
        "runtime_revision",
        "bound_file_count",
    ):
        expected = (
            len(declared_files)
            if key == "bound_file_count"
            else private.get(key)
        )
        if public.get(key) != expected:
            failures.append(f"public_{key}")
    result = {
        "passed": not failures,
        "bound_file_count": len(declared_files),
        "bundle_root_sha256": root_sha,
        "public_commitment_sha256": commitment,
        "failures": failures,
    }
    if failures:
        raise RuntimeError(
            "frozen native bundle verification failed: "
            f"{failures}"
        )
    return result


def build_frozen_bundle(
    *,
    bundle_root: Path,
    scenario_path: Path,
    instance_spec_path: Path,
    source_commit: str,
    runtime_revision: str,
    salt: str | None = None,
    excluded_relative_paths: Iterable[str] = (),
) -> FrozenBundle:
    """Bind one exact pre-model native bundle to a salted commitment."""

    root = bundle_root.resolve()
    scenario = scenario_path.resolve()
    instance = instance_spec_path.resolve()
    for path in (scenario, instance):
        path.relative_to(root)
    excluded = {
        Path(value).as_posix() for value in excluded_relative_paths
    }
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    if not files:
        raise ValueError("cannot freeze an empty native bundle")
    scenario_payload = json.loads(scenario.read_text(encoding="utf-8"))
    instance_payload = json.loads(instance.read_text(encoding="utf-8"))
    instance_semantic_sha = hashlib.sha256(
        _canonical(instance_payload)
    ).hexdigest()
    declared = str(scenario_payload.get("instance_spec_sha256", ""))
    if declared != instance_semantic_sha:
        raise ValueError(
            "scenario does not bind the canonical instance specification"
        )
    manifest = {
        "schema_version": "1.0",
        "scenario_id": str(scenario_payload["scenario_id"]),
        "source_commit": source_commit,
        "runtime_revision": runtime_revision,
        "scenario_sha256": file_sha256(scenario),
        "instance_spec_semantic_sha256": instance_semantic_sha,
        "files": files,
    }
    root_sha = hashlib.sha256(_canonical(manifest)).hexdigest()
    secret_salt = salt or secrets.token_hex(32)
    commitment = hashlib.sha256(
        f"{secret_salt}:{root_sha}".encode("utf-8")
    ).hexdigest()
    frozen_at = datetime.now(UTC).isoformat()
    private = {
        **manifest,
        "bundle_root_sha256": root_sha,
        "commitment_salt": secret_salt,
        "public_commitment_sha256": commitment,
        "frozen_at": frozen_at,
        "status": "active",
    }
    public = {
        "schema_version": "1.0",
        "scenario_id": manifest["scenario_id"],
        "source_commit": source_commit,
        "runtime_revision": runtime_revision,
        "public_commitment_sha256": commitment,
        "frozen_at": frozen_at,
        "status": "frozen_before_model_access",
        "bound_file_count": len(files),
    }
    return FrozenBundle(
        private_attestation=private,
        public_commitment=public,
    )


def append_usage_event(
    *,
    ledger_path: Path,
    event: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append lifecycle state without modifying the frozen task bundle."""

    allowed = {
        "generated",
        "frozen",
        "evaluation_locked",
        "consumed",
        "retired",
    }
    if event not in allowed:
        raise ValueError(f"unsupported usage event: {event}")
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    else:
        ledger = {"schema_version": "1.0", "events": []}
    previous = (
        str(ledger["events"][-1]["event"])
        if ledger["events"]
        else None
    )
    transitions = {
        None: {"generated", "frozen"},
        "generated": {"frozen"},
        "frozen": {"evaluation_locked", "retired"},
        "evaluation_locked": {"consumed", "retired"},
        "consumed": {"retired"},
        "retired": set(),
    }
    if event not in transitions.get(previous, set()):
        raise ValueError(
            f"invalid usage-ledger transition: {previous!r} -> {event!r}"
        )
    event_details = dict(details or {})
    if event == "frozen":
        commitment = str(
            event_details.get("public_commitment_sha256", "")
        )
        if not commitment:
            raise ValueError("frozen event must bind a public commitment")
        ledger["public_commitment_sha256"] = commitment
    elif previous is not None and previous != "generated":
        commitment = str(ledger.get("public_commitment_sha256", ""))
        if not commitment:
            raise ValueError("usage ledger is missing its public commitment")
        event_details["public_commitment_sha256"] = commitment
    record = {
        "event": event,
        "recorded_at": datetime.now(UTC).isoformat(),
        "details": event_details,
    }
    ledger["events"].append(record)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return record


__all__ = [
    "FrozenBundle",
    "append_usage_event",
    "build_frozen_bundle",
    "file_sha256",
    "verify_frozen_bundle",
]
