from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.erpnext_manufacturing_state_evidence import (
    ERPNextManufacturingStateEvidenceError,
    build_manufacturing_state_evidence,
)


class ERPNextManufacturingStateEvidenceTests(unittest.TestCase):
    def test_reset_and_boundary_bind_exact_native_state(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix.json"
            prefix.write_text('{"scenario_id":"manufacturing-1"}\n')
            manifest = self._bundle(root / "bundle")
            reset = build_manufacturing_state_evidence(
                scenario_id="manufacturing-1",
                instance_id="dev-001",
                variant_id="committed",
                phase="reset",
                prefix_path=prefix,
                bundle_manifest_path=manifest,
                state={"corrective_job_card": {"docstatus": 0}},
            )
            reset_path = root / "reset.json"
            self._write_json(reset_path, reset)
            boundary_state = {
                "corrective_job_card": {"docstatus": 1},
                "rq_jobs": [],
                "quality_release_delivery": {"reference": "JC-1"},
            }
            failure_path = root / "failure.json"
            self._write_json(
                failure_path,
                {
                    "schema_version": "0.1",
                    "artifact_type": "erpnext_manufacturing_failure_boundary",
                    "scenario_id": "manufacturing-1",
                    "variant": "committed",
                    "phase": "boundary",
                    "surface_error": "connection_lost_before_confirmation",
                    "latest_attempt": {
                        "tool": "submit_document",
                        "result": {
                            "ok": False,
                            "error": "connection_lost_before_confirmation",
                        },
                    },
                    "boundary_evidence": boundary_state,
                    "boundary_validation": {"passed": True},
                },
            )
            boundary = build_manufacturing_state_evidence(
                scenario_id="manufacturing-1",
                instance_id="dev-001",
                variant_id="committed",
                phase="boundary",
                prefix_path=prefix,
                bundle_manifest_path=manifest,
                state=boundary_state,
                failure_report_path=failure_path,
                reset_evidence_path=reset_path,
            )
            self.assertTrue(boundary["boundary_validation_passed"])
            self.assertEqual(
                boundary["visible_failure"]["error"],
                "connection_lost_before_confirmation",
            )
            self.assertEqual(
                boundary["reset_snapshot_sha256"],
                hashlib.sha256(reset_path.read_bytes()).hexdigest(),
            )

    def test_boundary_rejects_state_not_proven_by_failure_report(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix.json"
            prefix.write_text("{}\n")
            manifest = self._bundle(root / "bundle")
            reset = build_manufacturing_state_evidence(
                scenario_id="manufacturing-1",
                instance_id="dev-001",
                variant_id="committed",
                phase="reset",
                prefix_path=prefix,
                bundle_manifest_path=manifest,
                state={},
            )
            reset_path = root / "reset.json"
            self._write_json(reset_path, reset)
            failure_path = root / "failure.json"
            self._write_json(
                failure_path,
                {
                    "schema_version": "0.1",
                    "artifact_type": "erpnext_manufacturing_failure_boundary",
                    "scenario_id": "manufacturing-1",
                    "variant": "committed",
                    "phase": "boundary",
                    "latest_attempt": {"result": {"ok": False}},
                    "boundary_evidence": {"work_order": {"status": "Open"}},
                    "boundary_validation": {"passed": True},
                },
            )
            with self.assertRaisesRegex(
                ERPNextManufacturingStateEvidenceError,
                "difference paths",
            ):
                build_manufacturing_state_evidence(
                    scenario_id="manufacturing-1",
                    instance_id="dev-001",
                    variant_id="committed",
                    phase="boundary",
                    prefix_path=prefix,
                    bundle_manifest_path=manifest,
                    state={"work_order": {"status": "Completed"}},
                    failure_report_path=failure_path,
                    reset_evidence_path=reset_path,
                )

    def test_terminal_queue_audit_visibility_drift_is_not_boundary_drift(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix.json"
            prefix.write_text("{}\n")
            manifest = self._bundle(root / "bundle")
            reset = build_manufacturing_state_evidence(
                scenario_id="manufacturing-1",
                instance_id="dev-001",
                variant_id="committed",
                phase="reset",
                prefix_path=prefix,
                bundle_manifest_path=manifest,
                state={},
            )
            reset_path = root / "reset.json"
            self._write_json(reset_path, reset)
            failure_path = root / "failure.json"
            stable_state = {
                "work_order": {"status": "Open"},
                "rq_jobs": [],
            }
            self._write_json(
                failure_path,
                {
                    "schema_version": "0.1",
                    "artifact_type": "erpnext_manufacturing_failure_boundary",
                    "scenario_id": "manufacturing-1",
                    "variant": "committed",
                    "phase": "boundary",
                    "surface_error": "connection_lost_before_confirmation",
                    "latest_attempt": {"result": {"ok": False}},
                    "boundary_evidence": stable_state,
                    "boundary_validation": {"passed": True},
                },
            )
            captured_state = {
                **stable_state,
                "rq_jobs": [{"name": "job-1", "status": "finished"}],
            }
            boundary = build_manufacturing_state_evidence(
                scenario_id="manufacturing-1",
                instance_id="dev-001",
                variant_id="committed",
                phase="boundary",
                prefix_path=prefix,
                bundle_manifest_path=manifest,
                state=captured_state,
                failure_report_path=failure_path,
                reset_evidence_path=reset_path,
            )
            self.assertEqual(boundary["state"], captured_state)
            self.assertIn("failure_state_semantic_fingerprint", boundary)

    def test_pending_queue_job_visibility_drift_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix.json"
            prefix.write_text("{}\n")
            manifest = self._bundle(root / "bundle")
            reset = build_manufacturing_state_evidence(
                scenario_id="manufacturing-1",
                instance_id="dev-001",
                variant_id="pending",
                phase="reset",
                prefix_path=prefix,
                bundle_manifest_path=manifest,
                state={},
            )
            reset_path = root / "reset.json"
            self._write_json(reset_path, reset)
            failure_path = root / "failure.json"
            self._write_json(
                failure_path,
                {
                    "schema_version": "0.1",
                    "artifact_type": "erpnext_manufacturing_failure_boundary",
                    "scenario_id": "manufacturing-1",
                    "variant": "pending",
                    "phase": "boundary",
                    "latest_attempt": {"result": {"ok": False}},
                    "boundary_evidence": {
                        "work_order": {"status": "Open"},
                        "rq_jobs": [{"name": "job-1", "status": "queued"}],
                    },
                    "boundary_validation": {"passed": True},
                },
            )
            with self.assertRaisesRegex(
                ERPNextManufacturingStateEvidenceError,
                "difference paths",
            ):
                build_manufacturing_state_evidence(
                    scenario_id="manufacturing-1",
                    instance_id="dev-001",
                    variant_id="pending",
                    phase="boundary",
                    prefix_path=prefix,
                    bundle_manifest_path=manifest,
                    state={"work_order": {"status": "Open"}, "rq_jobs": []},
                    failure_report_path=failure_path,
                    reset_evidence_path=reset_path,
                )

    def test_async_boundary_bundle_may_intentionally_keep_workers_stopped(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix.json"
            prefix.write_text("{}\n")
            manifest = self._bundle(root / "bundle")
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["running_services"] = [
                service
                for service in payload["running_services"]
                if service not in {"queue-short", "queue-long"}
            ]
            self._write_json(manifest, payload)
            reset = build_manufacturing_state_evidence(
                scenario_id="manufacturing-1",
                instance_id="dev-001",
                variant_id="async_job_pending",
                phase="reset",
                prefix_path=prefix,
                bundle_manifest_path=manifest,
                state={"rq_jobs": [{"name": "job-1", "status": "queued"}]},
            )
            self.assertNotIn("queue-short", reset["bundle"]["running_services"])
            self.assertNotIn("queue-long", reset["bundle"]["running_services"])

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
            "site_crypto": ("site-crypto.json", b"crypto"),
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
                "schema_version": "1.2",
                "capture_mode": "simultaneous_service_quiescence",
                "running_services": [
                    "redis-queue",
                    "queue-fault",
                    "backend",
                    "queue-short",
                    "queue-long",
                    "websocket",
                    "frontend",
                    "fault-gateway",
                    "remittance",
                ],
                "files": files,
            },
        )
        return manifest


if __name__ == "__main__":
    unittest.main()
