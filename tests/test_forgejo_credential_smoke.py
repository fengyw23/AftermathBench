from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import scripts.smoke_forgejo_credentials as smoke


class ForgejoCredentialSmokeTests(unittest.TestCase):
    @patch.object(smoke, "ForgejoWebSession")
    @patch.object(smoke, "ForgejoAPI")
    def test_checks_api_identity_and_web_login(
        self,
        api_type: Mock,
        web_type: Mock,
    ) -> None:
        api_type.return_value.get.return_value = {"login": "owner"}
        web_type.return_value.signed_in = True
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            credentials = root / "credentials.json"
            output = root / "result.json"
            credentials.write_text(
                json.dumps(
                    {
                        "base_url": "http://api.invalid",
                        "web_base_url": "http://web.invalid",
                        "username": "owner",
                        "password": "password",
                        "token": "token",
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "sys.argv",
                [
                    "smoke",
                    "--credentials",
                    str(credentials),
                    "--output",
                    str(output),
                ],
            ):
                self.assertEqual(smoke.main(), 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(payload["api_token_passed"])
            self.assertTrue(payload["web_login_passed"])
            web_type.return_value.login.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
