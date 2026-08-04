from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .strict_json import load_json_strict


class ERPNextSalesReturnStateEvidenceError(ValueError):
    """Raised when an ERPNext state capture is not bound to native sources."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_state_fingerprint(state: dict[str, Any]) -> str:
    encoded = json.dumps(
        state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def json_difference_paths(
    expected: Any,
    actual: Any,
    *,
    limit: int = 20,
) -> tuple[str, ...]:
    """Return bounded JSON paths without exposing mismatched values."""

    differences: list[str] = []

    def visit(left: Any, right: Any, path: str) -> None:
        if len(differences) >= limit:
            return
        if type(left) is not type(right):
            differences.append(path)
            return
        if isinstance(left, dict):
            for key in sorted(set(left) | set(right), key=str):
                child = f"{path}.{key}"
                if key not in left or key not in right:
                    differences.append(child)
                else:
                    visit(left[key], right[key], child)
                if len(differences) >= limit:
                    return
            return
        if isinstance(left, list):
            if len(left) != len(right):
                differences.append(f"{path}.length")
            for index, (left_item, right_item) in enumerate(
                zip(left, right, strict=False)
            ):
                visit(left_item, right_item, f"{path}[{index}]")
                if len(differences) >= limit:
                    return
            return
        if left != right:
            differences.append(path)

    visit(expected, actual, "$")
    return tuple(differences)


def validate_bundle_manifest(
    manifest_path: str | Path,
) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    try:
        manifest = load_json_strict(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ERPNextSalesReturnStateEvidenceError(
            "native bundle manifest must be strict readable JSON"
        ) from error
    schema_version = (
        manifest.get("schema_version")
        if isinstance(manifest, dict)
        else None
    )
    expected_files = {
        "database": "database.sql",
        "redis_queue": "redis-queue.tar",
        "gateway_audit": "gateway-audit.tar",
        "remittance_audit": "remittance-audit.tar",
    }
    if schema_version == "1.2":
        expected_files["site_crypto"] = "site-crypto.json"
    if (
        not isinstance(manifest, dict)
        or set(manifest)
        != {
            "schema_version",
            "capture_mode",
            "running_services",
            "files",
        }
        or schema_version not in {"1.0", "1.2"}
        or manifest.get("capture_mode")
        != "simultaneous_service_quiescence"
        or not isinstance(manifest.get("running_services"), list)
        or set(manifest.get("files", {})) != set(expected_files)
    ):
        raise ERPNextSalesReturnStateEvidenceError(
            "native bundle manifest has an invalid contract"
        )
    services = tuple(map(str, manifest["running_services"]))
    if not services or len(services) != len(set(services)):
        raise ERPNextSalesReturnStateEvidenceError(
            "native bundle running services must be non-empty and unique"
        )
    required_services = {
        "redis-queue",
        "queue-fault",
        "backend",
        "websocket",
        "frontend",
        "fault-gateway",
        "remittance",
    }
    if not required_services <= set(services):
        raise ERPNextSalesReturnStateEvidenceError(
            "native bundle omits a required running service"
        )
    for key, expected_name in expected_files.items():
        declaration = manifest["files"].get(key)
        if (
            not isinstance(declaration, dict)
            or set(declaration) != {"path", "bytes", "sha256"}
            or declaration.get("path") != expected_name
            or type(declaration.get("bytes")) is not int
            or declaration["bytes"] < 1
        ):
            raise ERPNextSalesReturnStateEvidenceError(
                f"native bundle file declaration is invalid: {key}"
            )
        source = path.parent / expected_name
        if (
            not source.is_file()
            or source.stat().st_size != declaration["bytes"]
            or file_sha256(source) != declaration.get("sha256")
        ):
            raise ERPNextSalesReturnStateEvidenceError(
                f"native bundle file is not exact: {key}"
            )
    return manifest


def build_state_evidence(
    *,
    scenario_id: str,
    instance_id: str,
    variant_id: str,
    phase: str,
    prefix_path: str | Path,
    bundle_manifest_path: str | Path,
    state: dict[str, Any],
    failure_report_path: str | Path | None = None,
    reset_evidence_path: str | Path | None = None,
    artifact_type: str = "erpnext_sales_return_state_evidence",
    failure_artifact_type: str = "erpnext_sales_return_failure_boundary",
) -> dict[str, Any]:
    if not artifact_type or not failure_artifact_type:
        raise ERPNextSalesReturnStateEvidenceError(
            "state and failure artifact types must be non-empty"
        )
    if phase not in {"reset", "boundary"}:
        raise ERPNextSalesReturnStateEvidenceError(
            "state evidence phase must be reset or boundary"
        )
    if not scenario_id or not instance_id or not variant_id:
        raise ERPNextSalesReturnStateEvidenceError(
            "state evidence identity fields must be non-empty"
        )
    prefix_file = Path(prefix_path).resolve()
    manifest_file = Path(bundle_manifest_path).resolve()
    if not prefix_file.is_file():
        raise ERPNextSalesReturnStateEvidenceError(
            "state evidence prefix file is missing"
        )
    bundle = validate_bundle_manifest(manifest_file)
    failure_report: dict[str, Any] | None = None
    failure_file: Path | None = None
    reset_file: Path | None = None
    if phase == "reset":
        if failure_report_path is not None or reset_evidence_path is not None:
            raise ERPNextSalesReturnStateEvidenceError(
                "reset capture cannot bind failure or reset evidence"
            )
    else:
        if failure_report_path is None or reset_evidence_path is None:
            raise ERPNextSalesReturnStateEvidenceError(
                "boundary capture requires failure and reset evidence"
            )
        failure_file = Path(failure_report_path).resolve()
        reset_file = Path(reset_evidence_path).resolve()
        try:
            failure_report = load_json_strict(failure_file)
            reset_evidence = load_json_strict(reset_file)
        except (
            OSError,
            UnicodeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise ERPNextSalesReturnStateEvidenceError(
                "boundary sources must be strict readable JSON"
            ) from error
        if (
            not isinstance(failure_report, dict)
            or failure_report.get("schema_version") != "1.0"
            or failure_report.get("artifact_type") != failure_artifact_type
            or failure_report.get("scenario_id") != scenario_id
            or failure_report.get("variant") != variant_id
            or failure_report.get("phase") != "boundary"
            or failure_report.get("boundary_validation", {}).get("passed")
            is not True
        ):
            raise ERPNextSalesReturnStateEvidenceError(
                "failure report does not prove the captured boundary state"
            )
        reported_state = failure_report.get("failure_boundary_evidence")
        if reported_state != state:
            differences = json_difference_paths(reported_state, state)
            detail = ", ".join(differences) or "<unknown>"
            raise ERPNextSalesReturnStateEvidenceError(
                "failure report does not prove the captured boundary state; "
                f"difference paths: {detail}"
            )
        if (
            not isinstance(reset_evidence, dict)
            or reset_evidence.get("artifact_type") != artifact_type
            or reset_evidence.get("scenario_id") != scenario_id
            or reset_evidence.get("instance_id") != instance_id
            or reset_evidence.get("variant_id") != variant_id
            or reset_evidence.get("phase") != "reset"
            or reset_evidence.get("reset_verified") is not True
        ):
            raise ERPNextSalesReturnStateEvidenceError(
                "boundary reset evidence is not the matching verified reset"
            )
    state_fingerprint = canonical_state_fingerprint(state)
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": artifact_type,
        "scenario_id": scenario_id,
        "instance_id": instance_id,
        "variant_id": variant_id,
        "phase": phase,
        "prefix_file_sha256": file_sha256(prefix_file),
        "bundle_manifest_file_sha256": file_sha256(manifest_file),
        "bundle": bundle,
        "state_fingerprint": state_fingerprint,
        "state": state,
    }
    if phase == "reset":
        payload["reset_verified"] = True
    else:
        assert failure_file is not None
        assert reset_file is not None
        assert failure_report is not None
        payload.update(
            {
                "reset_evidence_file_sha256": file_sha256(reset_file),
                # The native name records what was hashed.  The normalized
                # name binds the same bytes into the domain-neutral formal
                # evidence protocol.
                "reset_snapshot_sha256": file_sha256(reset_file),
                "failure_report_file_sha256": file_sha256(failure_file),
                "surface_result": failure_report["surface_result"],
                "visible_failure": failure_report["visible_failure"],
                "boundary_validation_passed": True,
            }
        )
    return payload


__all__ = [
    "ERPNextSalesReturnStateEvidenceError",
    "build_state_evidence",
    "canonical_state_fingerprint",
    "file_sha256",
    "json_difference_paths",
    "validate_bundle_manifest",
]
