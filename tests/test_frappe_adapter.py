import json
import unittest
from unittest.mock import patch

from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FrappeAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = FrappeHTTPAdapter(
            FrappeConfig(
                base_url="http://erp.test",
                api_key="key",
                api_secret="secret",
            )
        )

    @patch("urllib.request.urlopen")
    def test_resource_path_and_token_auth(self, urlopen) -> None:
        urlopen.return_value = _Response({"data": {"name": "ACC-PINV-1"}})
        result = self.adapter.get_resource("Purchase Invoice", "ACC-PINV-1")
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://erp.test/api/resource/Purchase%20Invoice/ACC-PINV-1",
        )
        self.assertEqual(request.get_header("Authorization"), "token key:secret")
        self.assertEqual(result["data"]["name"], "ACC-PINV-1")

    @patch("urllib.request.urlopen")
    def test_submit_delegates_to_native_frappe_method(self, urlopen) -> None:
        document = {
            "doctype": "Payment Entry",
            "name": "ACC-PAY-1",
            "modified": "2026-07-28 10:53:20.273925",
        }
        urlopen.side_effect = [
            _Response({"data": document}),
            _Response({"message": {"docstatus": 1}}),
        ]
        self.adapter.submit_document("Payment Entry", "ACC-PAY-1")
        request = urlopen.call_args_list[1].args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            request.full_url,
            "http://erp.test/api/method/frappe.client.submit",
        )
        self.assertEqual(payload, {"doc": document})

    def test_submit_refreshes_only_after_timestamp_mismatch(self) -> None:
        first = {
            "doctype": "Purchase Order",
            "name": "PUR-ORD-1",
            "modified": "old",
        }
        refreshed = {**first, "modified": "new"}
        with (
            patch.object(
                self.adapter,
                "get_resource",
                side_effect=[{"data": first}, {"data": refreshed}],
            ) as get_resource,
            patch.object(
                self.adapter,
                "call_method",
                side_effect=[
                    RuntimeError("TimestampMismatchError: refresh"),
                    {"message": {"docstatus": 1}},
                ],
            ) as call_method,
        ):
            result = self.adapter.submit_document(
                "Purchase Order",
                "PUR-ORD-1",
            )
        self.assertEqual(result["message"]["docstatus"], 1)
        self.assertEqual(get_resource.call_count, 2)
        self.assertEqual(
            call_method.call_args_list[1].args[1],
            {"doc": refreshed},
        )

    @patch("urllib.request.urlopen")
    def test_list_resource_encodes_fields_and_filters(self, urlopen) -> None:
        urlopen.return_value = _Response({"data": []})
        self.adapter.list_resources(
            "GL Entry",
            fields=["name", "voucher_no"],
            filters={"voucher_no": "ACC-PAY-1"},
            order_by="creation desc",
        )
        request = urlopen.call_args.args[0]
        self.assertIn("/api/resource/GL%20Entry?", request.full_url)
        self.assertIn("limit_page_length=100", request.full_url)
        self.assertIn("%22voucher_no%22", request.full_url)
        self.assertIn("order_by=creation+desc", request.full_url)


if __name__ == "__main__":
    unittest.main()
