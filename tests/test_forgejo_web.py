from __future__ import annotations

import unittest

from aftermath_bench.integrations.forgejo_web import parse_webhook_history


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


if __name__ == "__main__":
    unittest.main()
