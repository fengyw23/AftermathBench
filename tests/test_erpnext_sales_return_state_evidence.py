from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.erpnext_sales_return_state_evidence import (
    ERPNextSalesReturnStateEvidenceError,
    build_state_evidence,
    canonical_state_fingerprint,
)


class ERPNextSalesReturnStateEvidenceTest(unittest.TestCase):
    def test_reset_and_boundary_bind_exact_native_bundle_and_state(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix.json"
            prefix.write_text('{"scenario_id":"scenario-1"}\n')
            manifest = self._bundle(root / "bundle")
            state = {
                "sales_return": {"name": "DN-RET-1", "docstatus": 1},
                "rq_jobs": [],
                "pickup_delivery": None,
            }
            reset = build_state_evidence(
                scenario_id="scenario-1",
                instance_id="dev-001",
                variant_id="committed",
                phase="reset",
                prefix_path=prefix,
                bundle_manifest_path=manifest,
                state={"sales_return": {"docstatus": 0}},
            )
            reset_path = root / "reset.json"
            self._write_json(reset_path, reset)
            failure_path = root / "failure.json"
            self._write_json(
                failure_path,
                {
                    "schema_version": "1.0",
                    "artifact_type": (
                        "erpnext_sales_return_failure_boundary"
                    ),
                    "scenario_id": "scenario-1",
                    "variant": "committed",
                    "phase": "boundary",
                    "surface_result": "connection lost",
                    "visible_failure": {
                        "ok": False,
                        "error": "connection_lost_before_confirmation",
                    },
                    "failure_boundary_evidence": state,
                    "boundary_validation": {"passed": True},
                },
            )

            boundary = build_state_evidence(
                scenario_id="scenario-1",
                instance_id="dev-001",
                variant_id="committed",
                phase="boundary",
                prefix_path=prefix,
                bundle_manifest_path=manifest,
                state=state,
                failure_report_path=failure_path,
                reset_evidence_path=reset_path,
            )

            self.assertTrue(reset["reset_verified"])
            self.assertTrue(boundary["boundary_validation_passed"])
            self.assertEqual(
                boundary["state_fingerprint"],
                canonical_state_fingerprint(state),
            )
            self.assertEqual(
                boundary["reset_evidence_file_sha256"],
                hashlib.sha256(reset_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                boundary["bundle"]["running_services"],
                [
                    "redis-queue",
                    "queue-fault",
                    "backend",
                    "fault-gateway",
                    "remittance",
                ],
            )

    def test_rejects_drifted_bundle_and_mismatched_failure_state(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix.json"
            prefix.write_text("{}\n")
            manifest = self._bundle(root / "bundle")
            (manifest.parent / "redis-queue.tar").write_bytes(b"drift")
            with self.assertRaisesRegex(
                ERPNextSalesReturnStateEvidenceError,
                "not exact: redis_queue",
            ):
                build_state_evidence(
                    scenario_id="scenario-1",
                    instance_id="dev-001",
                    variant_id="a",
                    phase="reset",
                    prefix_path=prefix,
                    bundle_manifest_path=manifest,
                    state={},
                )

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _bundle(self, root: Path) -> Path:
        root.mkdir()
        sources = {
            "database": ("database.sql", b"database"),
            "redis_queue": ("redis-queue.tar", b"queue"),
            "gateway_audit": ("gateway-audit.tar", b"gateway"),
            "remittance_audit": ("remittance-audit.tar", b"delivery"),
        }
        files = {}
        for key, (name, content) in sources.items():
            (root / name).write_bytes(content)
            files[key] = {
                "path": name,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        manifest = root / "bundle.json"
        self._write_json(
            manifest,
            {
                "schema_version": "1.0",
                "capture_mode": "simultaneous_service_quiescence",
                "running_services": [
                    "redis-queue",
                    "queue-fault",
                    "backend",
                    "fault-gateway",
                    "remittance",
                ],
                "files": files,
            },
        )
        return manifest


if __name__ == "__main__":
    unittest.main()
