from __future__ import annotations

import unittest

from aftermath_bench.evidence_replay import replay_graph
from scripts.build_forgejo_migration_admission import _observed_graph


class ForgejoMigrationAdmissionTest(unittest.TestCase):
    def test_graph_relations_replay_against_native_terminal_projection(self) -> None:
        prefix = {
            "scenario_id": "forgejo-migration-deployment-dev-001-r1",
            "instance_spec_sha256": "spec-sha",
            "repository": "customer-api-deployment",
            "source_commit": "commit-4",
            "change_issue_index": 1,
            "protected_issue_index": 2,
            "milestone_id": 10,
        }
        fixture = {
            "version": "2.0.0",
            "prior_version": "1.9.4",
            "migration_id": "migration-1",
            "artifact_digest": "sha256:artifact",
            "workflow_path": ".forgejo/workflows/deploy.yml",
            "migration_path": "migrations/1.sql",
            "artifact_manifest_path": "deploy/2.0.0.json",
            "production_environment": "production",
            "protected_environment": "staging-next",
            "release_tag": "v2.0.0",
        }
        evidence = {
            "repository": prefix["repository"],
            "main_branch": {"name": "main"},
            "source_commit": prefix["source_commit"],
            "files": {
                "workflow": {"path": fixture["workflow_path"], "sha": "w"},
                "migration": {"path": fixture["migration_path"], "sha": "m"},
                "manifest": {
                    "path": fixture["artifact_manifest_path"],
                    "sha": "a",
                },
            },
            "action_runs": [{"id": 101, "status": "success"}],
            "action_jobs": [{"id": 201, "run_id": 101, "status": "success"}],
            "migrations": [
                {
                    "migration_id": fixture["migration_id"],
                    "version": fixture["version"],
                    "attempt_count": 1,
                }
            ],
            "artifacts": [
                {
                    "version": fixture["version"],
                    "digest": fixture["artifact_digest"],
                }
            ],
            "production_deployments": [
                {
                    "environment": fixture["production_environment"],
                    "desired_version": fixture["version"],
                }
            ],
            "production_replicas": [
                {
                    "replica": replica,
                    "version": fixture["version"],
                    "status": "ready",
                }
                for replica in ("replica-a", "replica-b")
            ],
            "audits": [
                {
                    "event_key": "verify-production-2.0.0",
                    "attempt_count": 1,
                }
            ],
            "target_release": {"tag_name": fixture["release_tag"]},
            "prior_artifact": {
                "version": fixture["prior_version"],
                "digest": "sha256:prior",
                "attempt_count": 1,
            },
            "change_issue": {"number": 1, "state": "closed"},
            "protected_issue": {"number": 2, "state": "open"},
            "milestone": {"id": 10, "state": "closed"},
            "verification_comments": [
                {
                    "body": (
                        "Deployment verification: 2.0.0 "
                        f"{fixture['artifact_digest']}"
                    )
                }
            ],
            "protected_deployments": [
                {"environment": fixture["protected_environment"]}
            ],
            "protected_replicas": [
                {"replica": replica, "status": "ready"}
                for replica in ("replica-a", "replica-b")
            ],
        }
        graph = _observed_graph(prefix, fixture)
        replay = {
            "captures": [
                {"variant": f"variant-{index}", "evidence": evidence}
                for index in range(4)
            ]
        }

        results = replay_graph(graph, replay)

        self.assertGreaterEqual(len(graph["entities"]), 20)
        self.assertGreaterEqual(
            len({relation["type"] for relation in graph["relations"]}), 8
        )
        self.assertTrue(results)
        self.assertTrue(all(result.passed for result in results))


if __name__ == "__main__":
    unittest.main()
