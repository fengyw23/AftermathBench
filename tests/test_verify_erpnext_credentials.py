from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.verify_erpnext_credentials as verifier


class VerifyERPNextCredentialsTests(unittest.TestCase):
    def test_reports_only_a_safe_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            credentials = Path(directory) / "credentials.json"
            credentials.write_text(
                json.dumps({"api_key": "private-key", "api_secret": "private-secret"}),
                encoding="utf-8",
            )
            with (
                patch.object(
                    verifier.FrappeHTTPAdapter,
                    "get_resource",
                    return_value={
                        "data": {"name": "Administrator", "email": "private"}
                    },
                ),
                patch(
                    "sys.argv",
                    ["verify", "--credentials", str(credentials)],
                ),
                patch("builtins.print") as output,
            ):
                self.assertEqual(verifier.main(), 0)
            payload = json.loads(output.call_args.args[0])
            self.assertEqual(
                payload,
                {
                    "schema_version": "1.0",
                    "passed": True,
                    "credential_values_published": False,
                    "document_content_published": False,
                },
            )

    def test_authentication_failure_returns_two_without_error_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            credentials = Path(directory) / "credentials.json"
            credentials.write_text(
                json.dumps({"api_key": "private-key", "api_secret": "private-secret"}),
                encoding="utf-8",
            )
            with (
                patch.object(
                    verifier.FrappeHTTPAdapter,
                    "get_resource",
                    side_effect=RuntimeError("private server response"),
                ),
                patch(
                    "sys.argv",
                    ["verify", "--credentials", str(credentials)],
                ),
                patch("builtins.print") as output,
            ):
                self.assertEqual(verifier.main(), 2)
            text = output.call_args.args[0]
            self.assertFalse(json.loads(text)["passed"])
            self.assertNotIn("private", text)


if __name__ == "__main__":
    unittest.main()
