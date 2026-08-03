from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

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

    def test_restart_policy_does_not_assume_tracking_can_be_closed(self) -> None:
        forgejo = MagicMock()
        forgejo.list_action_runs.return_value = []
        deployment = MagicMock()
        stack = MagicMock()
        instance = SimpleNamespace(owner="owner", repository="repo")
        agent = ForgejoMigrationBaselineAgent(
            forgejo=forgejo,
            deployment=deployment,
            stack=stack,
            instance=instance,
            prefix={},
        )

        trace = agent.run("always_restart_runner")

        stack.start_action_runner.assert_called_once_with()
        deployment.state.assert_not_called()
        self.assertEqual([item["tool"] for item in trace], ["start_action_runner"])


if __name__ == "__main__":
    unittest.main()
