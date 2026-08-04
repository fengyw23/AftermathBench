from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aftermath_bench.runtime_services.deployment_target import DeploymentStore


class DeploymentTargetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = DeploymentStore(Path(self.temporary.name) / "target.sqlite3")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_native_job_requires_migration_and_artifact_then_updates_replicas(self) -> None:
        with self.assertRaisesRegex(ValueError, "prerequisites"):
            self.store.request_deployment(
                {"environment": "production", "version": "2.0.0", "migration_id": "m-2"}
            )
        self.store.apply_migration(
            {"migration_id": "m-2", "version": "2.0.0", "schema_hash": "sha256:schema"}
        )
        self.store.register_artifact(
            {"version": "2.0.0", "digest": "sha256:artifact", "source_commit": "abc123"}
        )
        job = self.store.request_deployment(
            {"environment": "production", "version": "2.0.0", "migration_id": "m-2"}
        )
        self.assertTrue(job["created"])
        self.assertEqual(self.store.state()["deployments"][0]["status"], "pending")
        completed = self.store.run_workers()
        self.assertEqual(completed["completed_job_ids"], [job["id"]])
        state = self.store.state()
        self.assertEqual(state["deployments"][0]["status"], "deployed")
        self.assertEqual(len(state["replicas"]), 2)
        self.assertTrue(all(row["version"] == "2.0.0" for row in state["replicas"]))

    def test_retries_are_audited_but_do_not_duplicate_effects(self) -> None:
        migration = {"migration_id": "m-2", "version": "2.0.0", "schema_hash": "sha256:schema"}
        first = self.store.apply_migration(migration)
        second = self.store.apply_migration(migration)
        self.assertTrue(first["first_application"])
        self.assertFalse(second["first_application"])
        self.assertEqual(second["attempt_count"], 2)

        event = {"event_key": "deploy-2", "event_type": "deployment_verified", "payload": {"version": "2.0.0"}}
        self.store.record_audit(event)
        repeated = self.store.record_audit(event)
        self.assertFalse(repeated["first_record"])
        self.assertEqual(repeated["attempt_count"], 2)
        self.assertEqual(len(self.store.state()["audit_events"]), 1)

    def test_signed_artifact_promotion_requires_matching_digest_not_migration(self) -> None:
        self.store.register_artifact(
            {
                "version": "6.2.0",
                "digest": "sha256:approved",
                "source_commit": "approved-commit",
            }
        )
        with self.assertRaisesRegex(ValueError, "approved artifact"):
            self.store.request_artifact_deployment(
                {
                    "environment": "clinical-production",
                    "version": "6.2.0",
                    "artifact_digest": "sha256:unapproved",
                }
            )
        job = self.store.request_artifact_deployment(
            {
                "environment": "clinical-production",
                "version": "6.2.0",
                "artifact_digest": "sha256:approved",
            }
        )
        self.assertTrue(job["created"])
        self.store.run_workers()
        retried = self.store.request_artifact_deployment(
            {
                "environment": "clinical-production",
                "version": "6.2.0",
                "artifact_digest": "sha256:approved",
            }
        )
        self.assertFalse(retried["created"])
        self.assertEqual(len(self.store.state()["rollout_jobs"]), 1)

    def test_conflicting_reuse_of_stable_identity_is_rejected(self) -> None:
        self.store.apply_migration(
            {"migration_id": "m-2", "version": "2.0.0", "schema_hash": "sha256:one"}
        )
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.store.apply_migration(
                {"migration_id": "m-2", "version": "2.0.0", "schema_hash": "sha256:two"}
            )


if __name__ == "__main__":
    unittest.main()
