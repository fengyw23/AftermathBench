from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .erpnext_sales_return_state_evidence import (
    canonical_state_fingerprint,
    file_sha256,
    json_difference_paths,
    validate_bundle_manifest,
)
from .strict_json import load_json_strict


class ERPNextManufacturingStateEvidenceError(ValueError):
    """Raised when a manufacturing capture is not bound to native state."""


def build_manufacturing_state_evidence(
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
) -> dict[str, Any]:
    if phase not in {"reset", "boundary"}:
        raise ERPNextManufacturingStateEvidenceError(
            "state evidence phase must be reset or boundary"
        )
    if not scenario_id or not instance_id or not variant_id:
        raise ERPNextManufacturingStateEvidenceError(
            "state evidence identity fields must be non-empty"
        )
    prefix_file = Path(prefix_path).resolve()
    manifest_file = Path(bundle_manifest_path).resolve()
    if not prefix_file.is_file():
        raise ERPNextManufacturingStateEvidenceError(
            "state evidence prefix file is missing"
        )
    bundle = validate_bundle_manifest(manifest_file)

    failure_report: dict[str, Any] | None = None
    failure_file: Path | None = None
    reset_file: Path | None = None
    if phase == "reset":
        if failure_report_path is not None or reset_evidence_path is not None:
            raise ERPNextManufacturingStateEvidenceError(
                "reset capture cannot bind failure or reset evidence"
            )
    else:
        if failure_report_path is None or reset_evidence_path is None:
            raise ERPNextManufacturingStateEvidenceError(
                "boundary capture requires failure and reset evidence"
            )
        failure_file = Path(failure_report_path).resolve()
        reset_file = Path(reset_evidence_path).resolve()
        try:
            failure_report = load_json_strict(failure_file)
            reset_evidence = load_json_strict(reset_file)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
            raise ERPNextManufacturingStateEvidenceError(
                "boundary sources must be strict readable JSON"
            ) from error
        if (
            not isinstance(failure_report, dict)
            or failure_report.get("schema_version") not in {"0.1", "1.0"}
            or failure_report.get("artifact_type")
            != "erpnext_manufacturing_failure_boundary"
            or failure_report.get("scenario_id") != scenario_id
            or failure_report.get("variant") != variant_id
            or failure_report.get("phase") != "boundary"
            or failure_report.get("boundary_validation", {}).get("passed")
            is not True
        ):
            raise ERPNextManufacturingStateEvidenceError(
                "failure report does not prove the captured boundary state"
            )
        reported_state = failure_report.get("boundary_evidence")
        if reported_state != state:
            differences = json_difference_paths(reported_state, state)
            detail = ", ".join(differences) or "<unknown>"
            raise ERPNextManufacturingStateEvidenceError(
                "failure report does not prove the captured boundary state; "
                f"difference paths: {detail}"
            )
        if (
            not isinstance(reset_evidence, dict)
            or reset_evidence.get("artifact_type")
            != "erpnext_manufacturing_state_evidence"
            or reset_evidence.get("scenario_id") != scenario_id
            or reset_evidence.get("instance_id") != instance_id
            or reset_evidence.get("variant_id") != variant_id
            or reset_evidence.get("phase") != "reset"
            or reset_evidence.get("reset_verified") is not True
        ):
            raise ERPNextManufacturingStateEvidenceError(
                "boundary reset evidence is not the matching verified reset"
            )

    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_type": "erpnext_manufacturing_state_evidence",
        "scenario_id": scenario_id,
        "instance_id": instance_id,
        "variant_id": variant_id,
        "phase": phase,
        "prefix_file_sha256": file_sha256(prefix_file),
        "bundle_manifest_file_sha256": file_sha256(manifest_file),
        "bundle": bundle,
        "state_fingerprint": canonical_state_fingerprint(state),
        "state": state,
    }
    if phase == "reset":
        payload["reset_verified"] = True
    else:
        assert failure_file is not None
        assert reset_file is not None
        assert failure_report is not None
        latest_attempt = failure_report.get("latest_attempt", {})
        visible_failure = latest_attempt.get("result")
        if not isinstance(visible_failure, dict):
            raise ERPNextManufacturingStateEvidenceError(
                "failure report omits the model-visible failure result"
            )
        payload.update(
            {
                "reset_evidence_file_sha256": file_sha256(reset_file),
                "reset_snapshot_sha256": file_sha256(reset_file),
                "failure_report_file_sha256": file_sha256(failure_file),
                "surface_result": failure_report.get("surface_error"),
                "visible_failure": visible_failure,
                "boundary_validation_passed": True,
            }
        )
    return payload


__all__ = [
    "ERPNextManufacturingStateEvidenceError",
    "build_manufacturing_state_evidence",
]
