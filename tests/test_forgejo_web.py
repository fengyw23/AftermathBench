from __future__ import annotations

import unittest

from aftermath_bench.integrations.forgejo_web import (
    ForgejoWebSession,
    WebhookDelivery,
    parse_webhook_history,
)


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return b""

    def geturl(self) -> str:
        return "http://forgejo/replayed"


class _RecordingOpener:
    def __init__(self) -> None:
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return _Response()


class ForgejoWebTest(unittest.TestCase):
    def test_history_parser_reads_native_uuid_and_status(self) -> None:
        html = """
        <div class="item">
          <span class="text green">ok</span>
          <span class="shortsha">delivery-success</span>
        </div>
        <div class="item">
          <span class="text red">failed</span>
          <span class="shortsha">delivery-failed</span>
        </div>
        <div class="item">
          <span class="text orange">pending</span>
          <span class="shortsha">delivery-pending</span>
        </div>
        """
        deliveries = parse_webhook_history(html)
        self.assertEqual(
            [(item.uuid, item.status) for item in deliveries],
            [
                ("delivery-success", "succeeded"),
                ("delivery-failed", "failed"),
                ("delivery-pending", "pending"),
            ],
        )

    def test_replay_matches_browser_same_origin_metadata(self) -> None:
        opener = _RecordingOpener()
        session = ForgejoWebSession(
            base_url="http://forgejo",
            username="admin",
            password="secret",
            opener=opener,
        )
        session.signed_in = True
        session.webhook_history = lambda *_args: (
            WebhookDelivery(uuid="delivery-failed", status="failed"),
        )

        result = session.replay_webhook(
            "owner",
            "repo",
            7,
            "delivery-failed",
        )

        request, timeout = opener.requests[-1]
        self.assertEqual(timeout, 15)
        self.assertEqual(request.method, "POST")
        self.assertEqual(
            request.get_header("Sec-fetch-site"),
            "same-origin",
        )
        self.assertEqual(result["status"], 200)


if __name__ == "__main__":
    unittest.main()
