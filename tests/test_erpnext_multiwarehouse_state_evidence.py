from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.erpnext_multiwarehouse_state_evidence import (
    FAILURE_ARTIFACT_TYPE,
    STATE_ARTIFACT_TYPE,
    build_multiwarehouse_state_evidence,
)


class ERPNextMultiwarehouseStateEvidenceTest(unittest.TestCase):
    def test_family_specific_labels_bind_boundary_to_matching_reset(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix.json"
            prefix.write_text('{"scenario_id":"transfer-1"}\n', encoding="utf-8")
            manifest = self._bundle(root / "bundle")
            reset = build_multiwarehouse_state_evidence(
                scenario_id="transfer-1", instance_id="dev-001", variant_id="v1",
                phase="reset", prefix_path=prefix, bundle_manifest_path=manifest,
                state={"second_leg_stock_entries": []},
            )
            reset_path = root / "reset.json"
            reset_path.write_text(json.dumps(reset), encoding="utf-8")
            state = {"second_leg_stock_entries": [{"name": "STE-2", "docstatus": 1}]}
            failure = root / "failure.json"
            failure.write_text(json.dumps({
                "schema_version": "1.0", "artifact_type": FAILURE_ARTIFACT_TYPE,
                "scenario_id": "transfer-1", "variant": "v1", "phase": "boundary",
                "surface_result": "connection lost", "visible_failure": {"ok": False},
                "boundary_evidence": state,
                "boundary_validation": {"passed": True},
            }), encoding="utf-8")
            boundary = build_multiwarehouse_state_evidence(
                scenario_id="transfer-1", instance_id="dev-001", variant_id="v1",
                phase="boundary", prefix_path=prefix, bundle_manifest_path=manifest,
                state=state, failure_report_path=failure, reset_evidence_path=reset_path,
            )
            self.assertEqual(reset["artifact_type"], STATE_ARTIFACT_TYPE)
            self.assertEqual(boundary["artifact_type"], STATE_ARTIFACT_TYPE)

    def _bundle(self, directory: Path) -> Path:
        directory.mkdir()
        entries = {}
        for key, filename in {
            "database": "database.sql", "redis_queue": "redis-queue.tar",
            "gateway_audit": "gateway-audit.tar", "remittance_audit": "remittance-audit.tar",
        }.items():
            path = directory / filename
            path.write_bytes(key.encode("utf-8"))
            import hashlib
            entries[key] = {"path": filename, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        manifest = directory / "bundle.json"
        manifest.write_text(json.dumps({"schema_version":"1.0", "capture_mode":"simultaneous_service_quiescence", "running_services":["redis-queue", "queue-fault", "backend", "websocket", "frontend", "fault-gateway", "remittance"], "files":entries}), encoding="utf-8")
        return manifest


if __name__ == "__main__":
    unittest.main()
