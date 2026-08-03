from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class ForgejoMigrationModelWorkflowTest(unittest.TestCase):
    def test_model_workflow_uses_native_boundary_and_public_tools(self) -> None:
        text = (
            repository_root()
            / ".github"
            / "workflows"
            / "forgejo-migration-model.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("ZHIPU_CODING_API_KEY", text)
        self.assertIn("run_forgejo_migration_boundary.py", text)
        self.assertIn("snapshot-migration-bundle", text)
        self.assertIn("restore-migration-bundle", text)
        self.assertIn("run-native-model", text)
        self.assertIn("summarize_native_model_runs.py", text)
        self.assertIn("--execution-control", text)
        boundary = text.index("run_forgejo_migration_boundary.py")
        model = text.index("run-native-model", boundary)
        self.assertLess(boundary, model)

    def test_model_credentials_are_not_available_during_prefix_build(self) -> None:
        text = (
            repository_root()
            / ".github"
            / "workflows"
            / "forgejo-migration-model.yml"
        ).read_text(encoding="utf-8")
        prefix = text.index("Build the persistent prefix")
        model = text.index("Run GLM on all matched migration boundaries")
        self.assertNotIn("AFTERMATH_API_KEY", text[prefix:model])


if __name__ == "__main__":
    unittest.main()
