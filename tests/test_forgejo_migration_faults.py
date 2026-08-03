from __future__ import annotations

import unittest

from aftermath_bench.integrations.forgejo_migration_faults import (
    FORGEJO_MIGRATION_VARIANTS,
    ForgejoMigrationFaultController,
)


class ForgejoMigrationFaultsTest(unittest.TestCase):
    def test_four_boundaries_share_surface_but_require_four_native_states(self) -> None:
        calls = []

        def requester(base_url, method, path, payload):
            calls.append((base_url, method, path, payload))
            return {"mode": payload["mode"]}

        controller = ForgejoMigrationFaultController(requester=requester)
        observed = {
            variant: controller.arm(variant)
            for variant in FORGEJO_MIGRATION_VARIANTS
        }
        self.assertEqual(len(observed), 4)
        self.assertEqual(
            {item.expected_run_status for item in observed.values()},
            {None, "waiting", "failure", "success"},
        )
        self.assertEqual(
            sum(not item.runner_enabled for item in observed.values()), 1
        )
        self.assertTrue(any(call[3]["mode"] == "suppress_request" for call in calls))
        self.assertTrue(any(call[3]["mode"] == "drop_response" for call in calls))


if __name__ == "__main__":
    unittest.main()
