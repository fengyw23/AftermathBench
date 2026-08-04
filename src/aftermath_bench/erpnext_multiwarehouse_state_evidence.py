"""Hash-bound state captures for the ERPNext multiwarehouse family.

The low-level capture format is shared with the sales-return family, but the
artifact labels remain family-specific.  This prevents a formal package from
accidentally binding a transfer boundary to a sales-return contract merely
because both use ERPNext snapshots.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .erpnext_sales_return_state_evidence import build_state_evidence

STATE_ARTIFACT_TYPE = "erpnext_multiwarehouse_state_evidence"
FAILURE_ARTIFACT_TYPE = "erpnext_multiwarehouse_failure_boundary"


def build_multiwarehouse_state_evidence(
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
    return build_state_evidence(
        scenario_id=scenario_id,
        instance_id=instance_id,
        variant_id=variant_id,
        phase=phase,
        prefix_path=prefix_path,
        bundle_manifest_path=bundle_manifest_path,
        state=state,
        failure_report_path=failure_report_path,
        reset_evidence_path=reset_evidence_path,
        artifact_type=STATE_ARTIFACT_TYPE,
        failure_artifact_type=FAILURE_ARTIFACT_TYPE,
        failure_state_field="boundary_evidence",
    )


__all__ = [
    "FAILURE_ARTIFACT_TYPE",
    "STATE_ARTIFACT_TYPE",
    "build_multiwarehouse_state_evidence",
]
