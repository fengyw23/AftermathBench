from __future__ import annotations

import json
import unittest

from aftermath_bench.integrations.forgejo_migration_instance import (
    DEFAULT_FORGEJO_MIGRATION_INSTANCE,
    migration_blueprint,
)
from aftermath_bench.integrations.forgejo_migration_prefix import deployment_workflow
from aftermath_bench.schema import repository_root


class ForgejoMigrationBlueprintTest(unittest.TestCase):
    def test_instance_file_matches_code_and_matrix_contract(self) -> None:
        root = repository_root()
        path = (
            root
            / "data"
            / "scenario_blueprints"
            / "forgejo-migration-deployment-dev-001"
            / "instance.json"
        )
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8")),
            DEFAULT_FORGEJO_MIGRATION_INSTANCE.as_dict(),
        )
        scenario = migration_blueprint(DEFAULT_FORGEJO_MIGRATION_INSTANCE)
        self.assertEqual(scenario["family"], "forgejo-migration-deployment")
        self.assertEqual(len(scenario["matched_variants"]), 4)
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


if __name__ == "__main__":
    unittest.main()
