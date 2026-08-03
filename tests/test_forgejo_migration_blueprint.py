from __future__ import annotations

import json
import unittest
from unittest.mock import ANY, MagicMock

from aftermath_bench.integrations.forgejo_migration_instance import (
    DEFAULT_FORGEJO_MIGRATION_INSTANCE,
    ForgejoMigrationInstanceSpec,
    migration_blueprint,
)
from aftermath_bench.integrations.forgejo_migration_prefix import (
    ForgejoMigrationPrefixBuilder,
    deployment_workflow,
)
from aftermath_bench.schema import repository_root


class ForgejoMigrationBlueprintTest(unittest.TestCase):
    def test_public_development_blueprint_is_instance_bound(self) -> None:
        root = repository_root()
        instance = ForgejoMigrationInstanceSpec.from_path(
            root
            / "data"
            / "instance_specs"
            / "forgejo-migration-public-dev-001.json"
        )
        rendered = json.loads(
            (
                root
                / "data"
                / "scenario_blueprints"
                / instance.scenario_id
                / "scenario.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            rendered,
            migration_blueprint(
                instance,
                instance_id="dev-001",
                benchmark_split="public_dev",
            ),
        )
        self.assertEqual(rendered["instance_spec_sha256"], instance.sha256)
        self.assertEqual(rendered["benchmark_split"], "public_dev")

    def test_instance_file_matches_code_and_matrix_contract(self) -> None:
        root = repository_root()
        path = (
            root
            / "data"
            / "scenario_blueprints"
            / "forgejo-migration-deployment-dev-002"
            / "instance.json"
        )
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8")),
            DEFAULT_FORGEJO_MIGRATION_INSTANCE.as_dict(),
        )
        scenario = migration_blueprint(DEFAULT_FORGEJO_MIGRATION_INSTANCE)
        self.assertEqual(scenario["family"], "forgejo-migration-deployment")
        self.assertEqual(len(scenario["matched_variants"]), 4)
        self.assertIn("verification note", scenario["user_instruction"])
        self.assertIn("approved artifact digest", scenario["user_instruction"])
        self.assertEqual(
            {item["recovery_signature_class"] for item in scenario["matched_variants"]},
            {
                "apply_missing_migration_then_deploy",
                "preserve_migration_and_rebuild_artifact",
                "resume_deployment_job",
                "verify_deployed_version",
            },
        )

    def test_workflow_uses_native_runner_and_five_real_state_transitions(self) -> None:
        workflow = deployment_workflow(DEFAULT_FORGEJO_MIGRATION_INSTANCE)
        self.assertIn("runs-on: aftermath-native", workflow)
        self.assertIn("resume_after_migration", workflow)
        self.assertIn("inputs.resume_after_migration != 'true'", workflow)
        for path in (
            "/migrations",
            "/artifacts",
            "/deployments",
            "/workers/run",
            "/audit-events",
        ):
            self.assertIn(path, workflow)
        self.assertNotIn("recommended", workflow.lower())
        self.assertNotIn("hidden", workflow.lower())

    def test_prefix_records_cross_system_writes_from_real_api_results(self) -> None:
        forgejo = MagicMock()
        forgejo.create_repository.return_value = {
            "id": 1,
            "owner": {"login": "aftermath"},
        }
        forgejo.edit_repository.return_value = {"has_releases": True}
        forgejo.create_milestone.return_value = {"id": 10}
        forgejo.create_issue.side_effect = [
            {"number": 1},
            {"number": 2},
        ]
        forgejo.create_file.side_effect = [
            {"commit": {"sha": f"commit-{index}"}} for index in range(1, 5)
        ]
        forgejo.create_release.return_value = {
            "tag_name": DEFAULT_FORGEJO_MIGRATION_INSTANCE.protected_release_tag
        }
        forgejo.create_branch.return_value = {"name": "protected/staging-next"}
        forgejo.create_branch_protection.return_value = {"rule_name": "protected/*"}

        deployment = MagicMock()
        deployment.apply_migration.return_value = {"first_application": True}
        deployment.register_artifact.return_value = {"first_registration": True}
        deployment.request_deployment.return_value = {"created": True}
        deployment.run_workers.return_value = {"completed_job_ids": [1]}
        deployment.state.return_value = {"deployments": [{"environment": "production"}]}

        prefix = ForgejoMigrationPrefixBuilder(forgejo, deployment).build()

        self.assertEqual(prefix.source_commit, "commit-4")
        self.assertEqual(prefix.change_issue_index, 1)
        self.assertEqual(prefix.protected_issue_index, 2)
        self.assertEqual(len(prefix.trace), 20)
        forgejo.edit_repository.assert_called_once_with(
            DEFAULT_FORGEJO_MIGRATION_INSTANCE.owner,
            DEFAULT_FORGEJO_MIGRATION_INSTANCE.repository,
            {"has_releases": True},
        )
        forgejo.create_release.assert_called_once_with(
            DEFAULT_FORGEJO_MIGRATION_INSTANCE.owner,
            DEFAULT_FORGEJO_MIGRATION_INSTANCE.repository,
            tag=DEFAULT_FORGEJO_MIGRATION_INSTANCE.protected_release_tag,
            target="main",
            title=(
                "Customer API "
                f"{DEFAULT_FORGEJO_MIGRATION_INSTANCE.prior_version}"
            ),
            body=ANY,
        )
        self.assertEqual(
            {event["system"] for event in prefix.trace},
            {"forgejo", "deployment-target"},
        )


if __name__ == "__main__":
    unittest.main()
