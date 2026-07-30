from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from aftermath_bench.integrations.forgejo_publication_recovery import (
    ForgejoPublicationEnvironment,
)
from aftermath_bench.integrations.forgejo_web import WebhookDelivery
from aftermath_bench.native_forgejo_publication_family import (
    FORGEJO_PUBLICATION_TOOL_DEFINITIONS,
)


class ForgejoPublicationContractTests(unittest.TestCase):
    def test_replay_and_receiver_identity_semantics_are_public(self) -> None:
        descriptions = {
            tool.name: tool.description
            for tool in FORGEJO_PUBLICATION_TOOL_DEFINITIONS
        }

        self.assertIn(
            "new X-Forgejo-Delivery UUID",
            descriptions["replay_webhook"],
        )
        self.assertIn(
            "not rebuilt from current Release state",
            descriptions["replay_webhook"],
        )
        self.assertIn(
            "not the receiver's idempotency identity",
            descriptions["get_external_delivery"],
        )
        self.assertIn(
            "different UUID represents a distinct receiver effect",
            descriptions["list_external_deliveries"],
        )
        self.assertNotIn(
            "replay only",
            descriptions["replay_webhook"].lower(),
        )

    def test_replay_result_does_not_mislabel_source_as_new_delivery(self) -> None:
        source = Path(
            "src/aftermath_bench/integrations/forgejo_web.py"
        ).read_text(encoding="utf-8")

        self.assertIn('"source_delivery_uuid": delivery_uuid', source)
        self.assertIn('"new_delivery_state": "not_checked"', source)
        self.assertNotIn('"delivery_uuid": delivery_uuid', source)

    @patch(
        "aftermath_bench.integrations.forgejo_publication_recovery.time.sleep"
    )
    def test_wait_requires_a_new_history_uuid(
        self,
        _sleep: object,
    ) -> None:
        class History:
            calls = 0

            def webhook_history(self, *_args):
                self.calls += 1
                if self.calls == 1:
                    return [WebhookDelivery("uuid-a", "succeeded")]
                return [
                    WebhookDelivery("uuid-a", "succeeded"),
                    WebhookDelivery("uuid-b", "succeeded"),
                ]

        def get_json(url: str):
            if url.endswith("/deliveries"):
                keys = ["uuid-a"] if history.calls <= 1 else [
                    "uuid-a",
                    "uuid-b",
                ]
                return {"deliveries": [{"key": key} for key in keys]}
            key = url.rsplit("/", 1)[-1]
            return {
                "key": key,
                "payload": {"release": {"tag_name": "v4.8.0"}},
                "attempt_count": 1,
            }

        history = History()
        environment = ForgejoPublicationEnvironment(
            api=object(),  # type: ignore[arg-type]
            web=history,  # type: ignore[arg-type]
            prefix={"owner": "org", "repository": "repo"},
            json_getter=get_json,
        )

        result = environment._wait_for_webhook_history_change(
            9,
            "v4.8.0",
            ("uuid-a",),
            2,
        )

        self.assertEqual(
            [row["uuid"] for row in result["new_history"]],
            ["uuid-b"],
        )
        self.assertEqual(
            [row["key"] for row in result["deliveries"]],
            ["uuid-b"],
        )


if __name__ == "__main__":
    unittest.main()
