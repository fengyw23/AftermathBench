from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class ForgejoMigrationWorkflowTest(unittest.TestCase):
    def test_workflow_builds_source_server_and_real_runner_before_dispatch(self) -> None:
        text = (
            repository_root()
            / ".github"
            / "workflows"
            / "forgejo-migration-runtime.yml"
        ).read_text(encoding="utf-8")
        ordered = (
            "build_forgejo_runtime.py",
            "manage_forgejo_stack.py up",
            "manage_forgejo_stack.py setup-runner",
            "build_forgejo_migration_prefix.py",
            "validate_forgejo_migration_runtime.py",
        )
        positions = [text.index(value) for value in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("AFTERMATH_MODEL_API_KEY", text)
        self.assertNotIn("run-native-model", text)
        self.assertIn("snapshot-migration-bundle", text)
        self.assertIn("restore-migration-bundle", text)
        self.assertIn("run_forgejo_migration_boundary.py", text)
        self.assertIn("--runner-disabled", text)
        self.assertIn("run_forgejo_migration_reference.py", text)
        self.assertIn("run_forgejo_migration_baseline.py", text)
        self.assertIn("Execute fixed recovery baselines", text)
        self.assertIn("build_forgejo_migration_admission.py", text)
        self.assertIn(
            "generated/forgejo-migration-deployment-dev-001-r1", text
        )


if __name__ == "__main__":
    unittest.main()
