from __future__ import annotations

import unittest

from aftermath_bench.integrations.forgejo_promotion_faults import (
    FORGEJO_PROMOTION_VARIANTS,
    ForgejoPromotionFaultController,
)


class ForgejoPromotionFaultsTest(unittest.TestCase):
    def test_six_boundaries_share_surface_but_span_real_stage_states(self) -> None:
        calls = []

        def requester(base_url, method, path, payload):
            calls.append((base_url, method, path, payload))
            return {"mode": payload["mode"]}

        controller = ForgejoPromotionFaultController(requester=requester)
        observed = {
            variant: controller.arm(variant)
            for variant in FORGEJO_PROMOTION_VARIANTS
        }
        self.assertEqual(len(observed), 6)
        self.assertEqual(
            {item.expected_run_status for item in observed.values()},
            {None, "waiting", "failure", "success"},
        )
        self.assertEqual(
            sum(not item.runner_enabled for item in observed.values()), 1
        )
        self.assertEqual(
            sum(item.finalize_release_metadata for item in observed.values()), 1
        )
        self.assertEqual(
            {item.workflow_inputs.get("stop_after") for item in observed.values()},
            {None, "bundle", "deployment"},
        )
        self.assertTrue(any(call[3]["mode"] == "suppress_request" for call in calls))


if __name__ == "__main__":
    unittest.main()
