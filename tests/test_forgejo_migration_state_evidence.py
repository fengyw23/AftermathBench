from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.forgejo_migration_state_evidence import (
    ForgejoMigrationStateEvidenceError,
    build_forgejo_migration_state_evidence,
    file_sha256,
    validate_forgejo_migration_boundary_replay,
)


class ForgejoMigrationStateEvidenceTests(unittest.TestCase):
    def test_reset_boundary_and_replay_bind_native_archives(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sources = self._sources(root)
            reset = build_forgejo_migration_state_evidence(
                **sources,
                state=self._state(),
                phase="reset",
            )
            reset_path = root / "reset.json"
            self._write(reset_path, reset)
            failure_path = root / "failure.json"
            self._write(
                failure_path,
                self._failure_report(self._state()),
            )
            boundary = build_forgejo_migration_state_evidence(
                **sources,
                state=self._state(),
                phase="boundary",
                surface_result="connection closed before acknowledgement",
                failure_report_path=failure_path,
                reset_evidence_path=reset_path,
            )
            self.assertTrue(boundary["boundary_validation_passed"])
            self.assertEqual(
                boundary["bundle"]["forgejo_sha256"],
                file_sha256(sources["forgejo_archive_path"]),
            )
            self.assertTrue(
                validate_forgejo_migration_boundary_replay(
                    boundary,
                    copy.deepcopy(boundary),
                )["passed"]
            )

    def test_boundary_rejects_report_state_drift(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sources = self._sources(root)
            reset = build_forgejo_migration_state_evidence(
                **sources,
                state=self._state(),
                phase="reset",
            )
            reset_path = root / "reset.json"
            self._write(reset_path, reset)
            failure_path = root / "failure.json"
            failure = self._failure_report(self._state())
            failure["deployment_state"]["migrations"].append(
                {"migration_id": "unexpected"}
            )
            self._write(failure_path, failure)
            with self.assertRaisesRegex(
                ForgejoMigrationStateEvidenceError,
                "does not prove",
            ):
                build_forgejo_migration_state_evidence(
                    **sources,
                    state=self._state(),
                    phase="boundary",
                    failure_report_path=failure_path,
                    reset_evidence_path=reset_path,
                )

    def test_archive_and_replay_drift_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sources = self._sources(root)
            Path(sources["forgejo_archive_path"]).write_bytes(b"tampered")
            with self.assertRaisesRegex(
                ForgejoMigrationStateEvidenceError,
                "does not bind",
            ):
                build_forgejo_migration_state_evidence(
                    **sources,
                    state=self._state(),
                    phase="reset",
                )

            sources = self._sources(root / "fresh")
            reset = build_forgejo_migration_state_evidence(
                **sources,
                state=self._state(),
                phase="reset",
            )
            reset_path = root / "fresh-reset.json"
            self._write(reset_path, reset)
            failure_path = root / "fresh-failure.json"
            self._write(failure_path, self._failure_report(self._state()))
            boundary = build_forgejo_migration_state_evidence(
                **sources,
                state=self._state(),
                phase="boundary",
                failure_report_path=failure_path,
                reset_evidence_path=reset_path,
            )
            replay = copy.deepcopy(boundary)
            replay["state"]["issues"][0]["state"] = "closed"
            with self.assertRaisesRegex(
                ForgejoMigrationStateEvidenceError,
                "not a validated|not byte-equivalent",
            ):
                validate_forgejo_migration_boundary_replay(boundary, replay)

    @staticmethod
    def _state() -> dict:
        deployment = {
            "migrations": [],
            "artifacts": [{"version": "3.3.2"}],
            "deployments": [{"environment": "preprod-next"}],
            "replicas": [],
            "audit_events": [],
        }
        return {
            "deployment_state": deployment,
            "releases": [{"tag_name": "v3.3.2"}],
            "issues": [{"number": 1, "state": "open"}],
            "milestone": {"id": 1, "state": "open"},
            "comments": [],
            "action_runs": [],
            "action_jobs": [],
        }

    @classmethod
    def _failure_report(cls, state: dict) -> dict:
        return {
            "schema_version": "1.0",
            "scenario_id": "forgejo-migration-public-dev-001",
            "instance_spec_sha256": "a" * 64,
            "variant": "dispatch_request_not_reached",
            "surface_result": {
                "ok": False,
                "error": "connection closed",
            },
            "visible_failure": {
                "ok": False,
                "error": "connection closed",
            },
            "action_run": None,
            "action_jobs": copy.deepcopy(state["action_jobs"]),
            "deployment_state": copy.deepcopy(state["deployment_state"]),
            "checks": {"surface_error_observed": True},
            "passed": True,
        }

    @classmethod
    def _sources(cls, root: Path) -> dict:
        root.mkdir(parents=True, exist_ok=True)
        prefix = root / "prefix.json"
        forgejo = root / "forgejo-data.tar.gz"
        deployment = root / "deployment-target-data.tar.gz"
        manifest = root / "bundle.json"
        cls._write(prefix, {"scenario_id": "forgejo-migration-public-dev-001"})
        forgejo.write_bytes(b"forgejo-state")
        deployment.write_bytes(b"deployment-state")
        cls._write(
            manifest,
            {
                "schema_version": "1.0",
                "capture_mode": (
                    "simultaneous_actions_and_deployment_quiescence"
                ),
                "runner_enabled": True,
                "forgejo_sha256": file_sha256(forgejo),
                "deployment_target_sha256": file_sha256(deployment),
            },
        )
        return {
            "scenario_id": "forgejo-migration-public-dev-001",
            "instance_id": "dev-001",
            "instance_spec_sha256": "a" * 64,
            "variant_id": "dispatch_request_not_reached",
            "prefix_path": prefix,
            "bundle_manifest_path": manifest,
            "forgejo_archive_path": forgejo,
            "deployment_target_archive_path": deployment,
        }

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
