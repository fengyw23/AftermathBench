from __future__ import annotations

import unittest

from aftermath_bench.integrations.forgejo_migration_baselines import (
    FORGEJO_MIGRATION_BASELINES,
    ForgejoMigrationBaselineAgent,
)


class ForgejoMigrationBaselinesTest(unittest.TestCase):
    def test_fixed_policies_are_explicit_and_none_is_variant_conditioned(self) -> None:
        self.assertEqual(len(FORGEJO_MIGRATION_BASELINES), 6)
        self.assertNotIn("oracle", FORGEJO_MIGRATION_BASELINES)
        self.assertNotIn("reference", FORGEJO_MIGRATION_BASELINES)
        self.assertNotIn("inspect_then_recover", FORGEJO_MIGRATION_BASELINES)

    def test_no_op_performs_no_queries_or_mutations(self) -> None:
        agent = ForgejoMigrationBaselineAgent(
            forgejo=object(),  # type: ignore[arg-type]
            deployment=object(),  # type: ignore[arg-type]
            stack=object(),  # type: ignore[arg-type]
            instance=object(),  # type: ignore[arg-type]
            prefix={},
        )
        self.assertEqual(agent.run("no_op"), ())


if __name__ == "__main__":
    unittest.main()
