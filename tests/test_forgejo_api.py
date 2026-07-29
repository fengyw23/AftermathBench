from __future__ import annotations

import json
import unittest
from typing import Self
from unittest.mock import Mock, patch

from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from scripts.validate_forgejo_runtime import (
    BASELINE_ISSUE,
    MUTATION_ISSUE,
    execute_phase,
)


class _Response:
    def __init__(self, payload: object):
        self.payload = payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class ForgejoAPITest(unittest.TestCase):
    def test_client_uses_token_auth_without_serializing_it(self) -> None:
        with patch(
            "urllib.request.urlopen",
            return_value=_Response({"name": "demo"}),
        ) as opener:
            result = ForgejoAPI(
                base_url="http://forgejo.invalid/api/v1",
                token="secret-token",
            ).create_repository("demo")
        request = opener.call_args.args[0]
        self.assertEqual(request.headers["Authorization"], "token secret-token")
        self.assertEqual(result["name"], "demo")

    def test_reset_validation_requires_the_mutation_to_disappear(self) -> None:
        client = Mock()
        client.list_issues.return_value = [{"title": BASELINE_ISSUE}]
        restored = execute_phase(client, "verify-restored")
        client.list_issues.return_value = [
            {"title": BASELINE_ISSUE},
            {"title": MUTATION_ISSUE},
        ]
        drifted = execute_phase(client, "verify-restored")
        self.assertTrue(restored["passed"])
        self.assertFalse(drifted["passed"])

    def test_merge_uses_the_native_forgejo_payload(self) -> None:
        with patch(
            "urllib.request.urlopen",
            return_value=_Response({"merged": True}),
        ) as opener:
            ForgejoAPI(
                base_url="http://forgejo.invalid/api/v1",
                token="secret-token",
            ).merge_pull_request(
                "aftermath",
                "release-control",
                2,
            )
        request = opener.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://forgejo.invalid/api/v1/repos/"
            "aftermath/release-control/pulls/2/merge",
        )
        self.assertEqual(
            json.loads(request.data),
            {"Do": "merge", "delete_branch_after_merge": False},
        )


if __name__ == "__main__":
    unittest.main()
