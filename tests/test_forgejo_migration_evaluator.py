from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from aftermath_bench.integrations.forgejo_migration_evaluator import (
    ForgejoMigrationEvaluator,
)
from aftermath_bench.integrations.forgejo_migration_instance import (
    DEFAULT_FORGEJO_MIGRATION_INSTANCE,
)


class ForgejoMigrationEvaluatorTest(unittest.TestCase):
    def _evaluator(self):
        spec = DEFAULT_FORGEJO_MIGRATION_INSTANCE
        target = MagicMock()
        target.state.return_value = {
            "migrations": [
                {
                    "migration_id": spec.migration_id,
                    "version": spec.version,
                    "schema_hash": spec.schema_hash,
                    "attempt_count": 1,
                }
            ],
            "artifacts": [
                {
                    "version": spec.version,
                    "digest": spec.artifact_digest,
                    "attempt_count": 1,
                },
                {
                    "version": spec.prior_version,
                    "digest": f"sha256:artifact-production-{spec.prior_version}",
                    "source_commit": f"seed-{spec.prior_version}",
                    "attempt_count": 1,
                },
            ],
            "deployments": [
                {
                    "environment": spec.production_environment,
                    "desired_version": spec.version,
                    "status": "deployed",
                },
                {
                    "environment": spec.protected_environment,
                    "desired_version": "2.1.0-beta.1",
                    "status": "deployed",
                },
            ],
            "replicas": [
                {
                    "environment": environment,
                    "replica": replica,
                    "version": version,
                    "artifact_digest": digest,
                    "status": "ready",
                }
                for environment, version, digest in (
                    (
                        spec.production_environment,
                        spec.version,
                        spec.artifact_digest,
                    ),
                    (
                        spec.protected_environment,
                        "2.1.0-beta.1",
                        "sha256:protected",
                    ),
                )
                for replica in ("replica-a", "replica-b")
            ],
            "audit_events": [
                {
                    "event_key": f"verify-{spec.production_environment}-{spec.version}",
                    "attempt_count": 1,
                }
            ],
        }
        forgejo = MagicMock()
        forgejo.list_releases.return_value = [
            {"tag_name": spec.release_tag},
        ]
        forgejo.list_issues.return_value = [
            {"number": 1, "state": "closed"},
            {"number": 2, "state": "open"},
        ]
        forgejo.get_milestone.return_value = {"state": "closed"}
        forgejo.list_issue_comments.return_value = [
            {
                "body": (
                    f"Deployment verification: {spec.version} "
                    f"{spec.artifact_digest}"
                )
            }
        ]
        forgejo.list_action_runs.return_value = [{"id": 101, "status": "success"}]
        forgejo.list_action_run_jobs.return_value = [
            {"id": 201, "run_id": 101, "status": "success"}
        ]
        protected = {
            "artifacts": [target.state.return_value["artifacts"][1]],
            "deployments": [target.state.return_value["deployments"][1]],
            "replicas": target.state.return_value["replicas"][2:],
        }
        prefix = {
            "milestone_id": 10,
            "change_issue_index": 1,
            "protected_issue_index": 2,
            "protected_state": protected,
        }
        return ForgejoMigrationEvaluator(forgejo, target, spec, prefix), forgejo

    def test_valid_terminal_state_passes_without_gold_trajectory_matching(self) -> None:
        evaluator, _ = self._evaluator()
        result = evaluator.evaluate(
            variant="workflow_completed_dispatch_response_lost"
        )
        self.assertTrue(result["recovery_integrity_pass"])
        self.assertTrue(result["passed"])
        self.assertIn("deployment_state", result["final_evidence"])
        self.assertIn("action_runs", result["final_evidence"])
        self.assertIn("action_jobs", result["final_evidence"])

    def test_duplicate_action_run_fails_protocol_safety_only(self) -> None:
        evaluator, forgejo = self._evaluator()
        forgejo.list_action_runs.return_value = [
            {"id": 101, "status": "success"},
            {"id": 102, "status": "success"},
        ]
        result = evaluator.evaluate(
            variant="workflow_completed_dispatch_response_lost"
        )
        self.assertTrue(result["components"]["goal_completion"])
        self.assertFalse(result["components"]["protocol_safety"])
        self.assertFalse(result["recovery_integrity_pass"])


if __name__ == "__main__":
    unittest.main()
