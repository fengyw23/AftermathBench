import http.client
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aftermath_bench.runtime_services.gateway import (
    GatewayAuditStore,
    GatewayState,
    make_gateway_handler,
)
from aftermath_bench.runtime_services.remittance import (
    DeliveryStore,
    extract_delivery_key,
)


class RemittanceServiceTest(unittest.TestCase):
    def test_duplicate_delivery_is_audited_but_not_applied_twice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = DeliveryStore(Path(directory) / "delivery.sqlite3")
            first = store.record({"payment_entry": "ACC-PAY-2026-00001"})
            second = store.record({"payment_entry": "ACC-PAY-2026-00001"})
            record = store.get("ACC-PAY-2026-00001")
            counts = store.counts()
            store.reset()
            reset_counts = store.counts()
        self.assertTrue(first.first_delivery)
        self.assertFalse(second.first_delivery)
        self.assertEqual(second.attempt_count, 2)
        self.assertEqual(record["attempt_count"], 2)
        self.assertEqual(counts, {"unique_deliveries": 1, "attempts": 2})
        self.assertEqual(
            reset_counts,
            {"unique_deliveries": 0, "attempts": 0},
        )

    def test_key_uses_visible_payment_identifier(self) -> None:
        self.assertEqual(
            extract_delivery_key({"doc": {"name": "ACC-PAY-9"}}),
            "ACC-PAY-9",
        )


class _UpstreamHandler(BaseHTTPRequestHandler):
    calls = 0

    def log_message(self, _format, *_args):
        return

    def do_POST(self):
        type(self).calls += 1
        body = json.dumps({"committed": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class GatewayServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        _UpstreamHandler.calls = 0
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
        threading.Thread(
            target=self.upstream.serve_forever,
            daemon=True,
        ).start()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state = GatewayState()
        self.audit = GatewayAuditStore(
            Path(self.temporary_directory.name) / "gateway.sqlite3"
        )
        self.gateway = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_gateway_handler(
                upstream_url=(
                    f"http://127.0.0.1:{self.upstream.server_address[1]}"
                ),
                state=self.state,
                audit=self.audit,
            ),
        )
        threading.Thread(target=self.gateway.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        self.gateway.shutdown()
        self.gateway.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()
        self.temporary_directory.cleanup()

    def _post(self) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.gateway.server_address[1],
            timeout=2,
        )
        try:
            connection.request(
                "POST",
                "/api/method/frappe.client.submit",
                body=b"{}",
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_normal_mode_forwards_request_and_response(self) -> None:
        status, body = self._post()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"committed": True})
        self.assertEqual(_UpstreamHandler.calls, 1)
        self.assertEqual(
            self.audit.events()[-1]["outcome"],
            "response_forwarded",
        )

    def test_suppress_mode_never_reaches_upstream(self) -> None:
        self.state.set("suppress_request")
        with self.assertRaises(
            (http.client.RemoteDisconnected, ConnectionResetError),
        ):
            self._post()
        self.assertEqual(_UpstreamHandler.calls, 0)
        self.assertEqual(
            self.audit.events()[-1]["outcome"],
            "request_suppressed",
        )

    def test_drop_response_waits_for_upstream_completion(self) -> None:
        self.state.set("drop_response")
        with self.assertRaises(
            (http.client.RemoteDisconnected, ConnectionResetError),
        ):
            self._post()
        self.assertEqual(_UpstreamHandler.calls, 1)
        event = self.audit.events()[-1]
        self.assertEqual(event["upstream_status"], 200)
        self.assertEqual(
            event["outcome"],
            "upstream_completed_response_dropped",
        )


if __name__ == "__main__":
    unittest.main()
