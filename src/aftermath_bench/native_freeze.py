from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .path_safety import safe_relative_path

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ZERO_SHA256 = "0" * 64


def _usage_event_digest(record: dict[str, Any]) -> str:
    payload = {
        key: record[key]
        for key in (
            "sequence",
            "event",
            "recorded_at",
            "previous_event_sha256",
            "details",
        )
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()


def validate_usage_ledger(ledger: dict[str, Any]) -> tuple[str, ...]:
    failures: list[str] = []
    if ledger.get("schema_version") != "2.0":
        failures.append("schema_version")
    events = ledger.get("events")
    if not isinstance(events, list):
        return (*failures, "events")
    previous = _ZERO_SHA256
    previous_name: str | None = None
    transitions = {
        None: {"generated", "frozen"},
        "generated": {"frozen"},
        "frozen": {"evaluation_locked", "retired"},
        "evaluation_locked": {"consumed", "retired"},
        "consumed": {"retired"},
        "retired": set(),
    }
    for index, record in enumerate(events, start=1):
        if not isinstance(record, dict):
            failures.append(f"event_object:{index}")
            continue
        name = str(record.get("event", ""))
        if record.get("sequence") != index:
            failures.append(f"event_sequence:{index}")
        if record.get("previous_event_sha256") != previous:
            failures.append(f"event_previous_hash:{index}")
        if name not in transitions.get(previous_name, set()):
            failures.append(f"event_transition:{index}")
        observed_hash = str(record.get("event_sha256", ""))
        if (
            _SHA256.fullmatch(observed_hash) is None
            or observed_hash != _usage_event_digest(record)
        ):
            failures.append(f"event_hash:{index}")
        previous = observed_hash
        previous_name = name
    if str(ledger.get("head_event_sha256", "")) != previous:
        failures.append("head_event_sha256")
    return tuple(failures)

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
    }
    for value in allowed_unbound_relative_paths:
        allowed_path = safe_relative_path(root, str(value))
        allowed.add(allowed_path.relative_to(root).as_posix())
    file_entries = list(private.get("files", []))
    declared_paths = [str(item.get("path", "")) for item in file_entries]
    declared_files = {
        path: item for path, item in zip(declared_paths, file_entries)
    }
    failures = []
    if len(declared_paths) != len(set(declared_paths)):
        failures.append("duplicate_declared_path")
    if declared_paths != sorted(declared_paths):
        failures.append("declared_paths_not_sorted")
    for observed_path in root.rglob("*"):
        if observed_path.is_symlink():
            failures.append(
                "symlink:" + observed_path.relative_to(root).as_posix()
            )
    for relative, item in declared_files.items():
        try:
            path = safe_relative_path(
                root,
                relative,
                must_exist=True,
                require_file=True,
            )
        except (OSError, ValueError):
            failures.append(f"missing:{relative}")
            continue
        if _SHA256.fullmatch(str(item.get("sha256", ""))) is None:
            failures.append(f"invalid_sha256:{relative}")
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
        ).encode()
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
        safe_relative_path(root, str(value))
        .relative_to(root)
        .as_posix()
        for value in excluded_relative_paths
    }
    files = []
    discovered = sorted(root.rglob("*"))
    symlinks = [path for path in discovered if path.is_symlink()]
    if symlinks:
        raise ValueError(
            "native bundle contains symbolic links: "
            + ", ".join(path.relative_to(root).as_posix() for path in symlinks)
        )
    for path in (item for item in discovered if item.is_file()):
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
        f"{secret_salt}:{root_sha}".encode()
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
    """Atomically append lifecycle state outside the frozen task bundle.

    The sibling ``.lock`` file is acquired with ``O_EXCL`` before the ledger is
    read.  Competing evaluation processes therefore cannot both observe a
    ``frozen`` head and independently append ``evaluation_locked``.  A stale
    lock fails closed and must be investigated rather than silently removed.
    """

    allowed = {
        "generated",
        "frozen",
        "evaluation_locked",
        "consumed",
        "retired",
    }
    if event not in allowed:
        raise ValueError(f"unsupported usage event: {event}")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = ledger_path.with_name(f".{ledger_path.name}.lock")
    lock_fd: int | None = None
    try:
        try:
            lock_fd = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as error:
            raise RuntimeError(
                f"usage ledger is locked by another process: {lock_path}"
            ) from error
        os.write(lock_fd, f"{os.getpid()}\n".encode())
        os.fsync(lock_fd)

        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger_failures = validate_usage_ledger(ledger)
            if ledger_failures:
                raise ValueError(
                    f"invalid usage ledger before append: {ledger_failures}"
                )
        else:
            ledger = {
                "schema_version": "2.0",
                "events": [],
                "head_event_sha256": _ZERO_SHA256,
            }
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
                raise ValueError(
                    "usage ledger is missing its public commitment"
                )
            event_details["public_commitment_sha256"] = commitment
        record = {
            "sequence": len(ledger["events"]) + 1,
            "event": event,
            "recorded_at": datetime.now(UTC).isoformat(),
            "previous_event_sha256": str(
                ledger.get("head_event_sha256", _ZERO_SHA256)
            ),
            "details": event_details,
        }
        record["event_sha256"] = _usage_event_digest(record)
        ledger["events"].append(record)
        ledger["head_event_sha256"] = record["event_sha256"]
        temporary = ledger_path.with_name(
            f".{ledger_path.name}.{secrets.token_hex(8)}.tmp"
        )
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(ledger, ensure_ascii=False, indent=2) + "\n"
                )
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(ledger_path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return record
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
            lock_path.unlink(missing_ok=True)


__all__ = [
    "FrozenBundle",
    "append_usage_event",
    "build_frozen_bundle",
    "file_sha256",
    "validate_usage_ledger",
    "verify_frozen_bundle",
]
