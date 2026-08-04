from __future__ import annotations

import unittest

from aftermath_bench.integrations.forgejo_migration_instance import (
    ForgejoMigrationInstanceSpec,
)
from scripts.generate_forgejo_migration_hidden_instance import build_instance


class GenerateForgejoMigrationHiddenInstanceTests(unittest.TestCase):
    def test_generated_instance_satisfies_native_schema(self) -> None:
        instance = ForgejoMigrationInstanceSpec(**build_instance("test-001"))
        instance.validate()
        self.assertIn("hidden-test-001", instance.scenario_id)
        self.assertNotEqual(instance.version, instance.prior_version)
        self.assertNotEqual(instance.release_tag, instance.protected_release_tag)

    def test_private_identity_is_fresh_per_instance(self) -> None:
        first = build_instance("test-001")
        second = build_instance("test-002")
        self.assertNotEqual(first["scenario_id"], second["scenario_id"])
        self.assertNotEqual(first["repository"], second["repository"])


if __name__ == "__main__":
    unittest.main()
