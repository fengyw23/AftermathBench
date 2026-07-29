from __future__ import annotations

import unittest

from aftermath_bench.integrations.forgejo_faults import (
    FORGEJO_FAULT_VARIANTS,
    ForgejoFaultController,
)


class ForgejoFaultControllerTest(unittest.TestCase):
    def test_variants_share_api_error_but_change_webhook_boundary(self) -> None:
        for variant in FORGEJO_FAULT_VARIANTS:
            with self.subTest(variant=variant):
                calls = []

                def requester(base_url, method, path, payload):
                    calls.append((base_url, method, path, payload))
                    return {"mode": payload["mode"]}

                controller = ForgejoFaultController(requester=requester)
                controller.arm(variant)
                api_modes = [
                    payload["mode"]
                    for url, _, _, payload in calls
                    if url.endswith("9091")
                ]
                webhook_modes = [
                    payload["mode"]
                    for url, _, _, payload in calls
                    if url.endswith("9093")
                ]
                expected_api = (
                    "suppress_request"
                    if variant == "merge_request_not_reached"
                    else "drop_response"
                )
                self.assertEqual(api_modes[-1], expected_api)
                if "receiver_accepted" in variant:
                    self.assertEqual(webhook_modes[-1], "drop_response")
                elif "delivery_request_not_reached" in variant:
                    self.assertEqual(
                        webhook_modes[-1],
                        "suppress_request",
                    )
                else:
                    self.assertEqual(webhook_modes[-1], "normal")

    def test_unknown_variant_is_rejected_before_mutation(self) -> None:
        calls = []
        controller = ForgejoFaultController(
            requester=lambda *args: calls.append(args) or {}
        )
        with self.assertRaisesRegex(ValueError, "unknown Forgejo"):
            controller.arm("invented_partial_commit")
        self.assertFalse(calls)


if __name__ == "__main__":
    unittest.main()
