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
        urlopen.return_value = _Response({"message": {"docstatus": 1}})
        self.adapter.submit_document("Payment Entry", "ACC-PAY-1")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            request.full_url,
            "http://erp.test/api/method/frappe.client.submit",
        )
        self.assertEqual(
            payload,
            {"doc": {"doctype": "Payment Entry", "name": "ACC-PAY-1"}},
        )

    @patch("urllib.request.urlopen")
    def test_list_resource_encodes_fields_and_filters(self, urlopen) -> None:
        urlopen.return_value = _Response({"data": []})
        self.adapter.list_resources(
            "GL Entry",
            fields=["name", "voucher_no"],
            filters={"voucher_no": "ACC-PAY-1"},
        )
        request = urlopen.call_args.args[0]
        self.assertIn("/api/resource/GL%20Entry?", request.full_url)
        self.assertIn("limit_page_length=100", request.full_url)
        self.assertIn("%22voucher_no%22", request.full_url)


if __name__ == "__main__":
    unittest.main()
