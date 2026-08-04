from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .strict_json import load_json_strict


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class FrozenHiddenRecord:
    formal_slot_id: str
    scenario_id: str
    domain_id: str
    family_id: str
    instance_id: str
    variant_count: int
    freeze_run_id: int
    public_commitment_sha256: str
    artifact_url: str
    evidence_path: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_sha(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _validate_receipt(
    receipt: dict[str, Any],
    *,
    record: dict[str, Any],
) -> None:
    if set(receipt) != {
        "schema_version",
        "artifact",
        "file_sha256",
        "commitment",
        "sealed_bundle",
        "result",
    } or receipt.get("schema_version") != "1.0":
        raise ValueError("frozen hidden receipt has an invalid contract")

    artifact = receipt["artifact"]
    file_sha256 = receipt["file_sha256"]
    commitment = receipt["commitment"]
    sealed = receipt["sealed_bundle"]
    result = receipt["result"]
    if not all(isinstance(item, dict) for item in (
        artifact,
        file_sha256,
        commitment,
        sealed,
        result,
    )):
        raise ValueError("frozen hidden receipt payloads must be objects")

    for name in ("result", "pre_model_commitment", "sealed_bundle"):
        _require_sha(file_sha256.get(name), label=f"file_sha256.{name}")

    scenario_id = str(record["scenario_id"])
    run_id = int(record["freeze_run_id"])
    public_commitment = str(record["public_commitment_sha256"])
    variant_count = int(record["variant_count"])
    if (
        artifact.get("run_id") != run_id
        or artifact.get("url") != record["artifact_url"]
        or commitment.get("scenario_id") != scenario_id
        or result.get("scenario_id") != scenario_id
        or sealed.get("source_run_id") != run_id
        or commitment.get("public_commitment_sha256") != public_commitment
        or result.get("public_commitment_sha256") != public_commitment
        or sealed.get("public_commitment_sha256") != public_commitment
        or commitment.get("source_commit") != result.get("source_commit")
        or sealed.get("source_commit") != result.get("source_commit")
        or commitment.get("runtime_revision") != result.get("runtime_revision")
        or commitment.get("status") != "frozen_before_model_access"
        or result.get("status") != "frozen_before_model_access"
        or sealed.get("lifecycle_status") != "frozen_unseen"
        or result.get("usage_state") != "frozen"
        or result.get("raw_hidden_bundle_published") is not False
        or result.get("admission", {}).get("passed") is not True
        or result.get("admission", {}).get("admitted_tier") != "hard"
        or result.get("reference", {}).get("case_count") != variant_count
        or result.get("reference", {}).get("pass_count") != variant_count
        or result.get("fixed_policies", {}).get("matched_group_solver_count") != 0
        or result.get("execution_control", {}).get("status")
        != "frozen_not_consumed"
        or result.get("execution_control", {}).get("gate_pass") is not False
    ):
        raise ValueError("frozen hidden receipt does not prove an unseen hard task")


def load_frozen_hidden_registry(
    path: str | Path,
    *,
    root: str | Path,
) -> tuple[FrozenHiddenRecord, ...]:
    root_path = Path(root).resolve()
    payload = load_json_strict(Path(path))
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "records"}
        or payload.get("schema_version") != "1.0"
        or not isinstance(payload.get("records"), list)
    ):
        raise ValueError("frozen hidden registry has an invalid contract")

    records: list[FrozenHiddenRecord] = []
    slots: set[str] = set()
    runs: set[int] = set()
    commitments: set[str] = set()
    for index, raw in enumerate(payload["records"]):
        if not isinstance(raw, dict) or set(raw) != {
            "formal_slot_id",
            "scenario_id",
            "domain_id",
            "family_id",
            "instance_id",
            "variant_count",
            "freeze_run_id",
            "public_commitment_sha256",
            "artifact_url",
            "evidence_path",
            "evidence_sha256",
        }:
            raise ValueError(f"frozen hidden registry record {index} is invalid")
        slot = str(raw["formal_slot_id"])
        expected_slot = (
            f"{raw['domain_id']}/{raw['family_id']}/{raw['instance_id']}"
        )
        run_id = raw["freeze_run_id"]
        variant_count = raw["variant_count"]
        commitment = _require_sha(
            raw["public_commitment_sha256"],
            label="public_commitment_sha256",
        )
        evidence_sha = _require_sha(
            raw["evidence_sha256"],
            label="evidence_sha256",
        )
        evidence_path = root_path / str(raw["evidence_path"])
        if (
            slot != expected_slot
            or raw["instance_id"] not in {"test-001", "test-002"}
            or type(run_id) is not int
            or run_id < 1
            or type(variant_count) is not int
            or variant_count < 1
            or not str(raw["scenario_id"])
            or not str(raw["artifact_url"]).startswith("https://github.com/")
            or not evidence_path.is_file()
            or _sha256(evidence_path) != evidence_sha
            or slot in slots
            or run_id in runs
            or commitment in commitments
        ):
            raise ValueError(f"frozen hidden registry record {index} is invalid")
        receipt = load_json_strict(evidence_path)
        if not isinstance(receipt, dict):
            raise ValueError("frozen hidden receipt must be an object")
        _validate_receipt(receipt, record=raw)
        records.append(
            FrozenHiddenRecord(
                formal_slot_id=slot,
                scenario_id=str(raw["scenario_id"]),
                domain_id=str(raw["domain_id"]),
                family_id=str(raw["family_id"]),
                instance_id=str(raw["instance_id"]),
                variant_count=variant_count,
                freeze_run_id=run_id,
                public_commitment_sha256=commitment,
                artifact_url=str(raw["artifact_url"]),
                evidence_path=str(raw["evidence_path"]),
            )
        )
        slots.add(slot)
        runs.add(run_id)
        commitments.add(commitment)
    return tuple(records)


__all__ = ["FrozenHiddenRecord", "load_frozen_hidden_registry"]
