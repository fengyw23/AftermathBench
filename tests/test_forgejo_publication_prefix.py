from __future__ import annotations

import unittest
from unittest.mock import patch

from aftermath_bench.integrations.forgejo_publication_prefix import (
    ForgejoPublicationPrefixBuilder,
)


class _PullStateClient:
    def __init__(self, states: list[dict[str, object]]) -> None:
        self.states = list(states)
        self.calls = 0

    def get_pull_request(
        self,
        owner: str,
        repository: str,
        index: int,
    ) -> dict[str, object]:
        del owner, repository, index
        state = self.states[min(self.calls, len(self.states) - 1)]
        self.calls += 1
        return state


class ForgejoPublicationPrefixTests(unittest.TestCase):
    @patch(
        "aftermath_bench.integrations.forgejo_publication_prefix.time.sleep"
    )
    def test_waits_for_native_mergeability(
        self,
        sleep: object,
    ) -> None:
        client = _PullStateClient(
            [
                {"mergeable": False, "state": "open"},
                {"mergeable": False, "state": "open"},
                {"mergeable": True, "state": "open"},
            ]
        )
        builder = ForgejoPublicationPrefixBuilder(client)  # type: ignore[arg-type]

        observed = builder._wait_for_pull_mergeable(
            "owner",
            "repo",
            2,
            attempts=3,
            interval_seconds=0.01,
        )

        self.assertTrue(observed["mergeable"])
        self.assertEqual(client.calls, 3)
        self.assertEqual(sleep.call_count, 2)  # type: ignore[attr-defined]

    @patch(
        "aftermath_bench.integrations.forgejo_publication_prefix.time.sleep"
    )
    def test_rejects_prefix_if_pull_never_becomes_mergeable(
        self,
        sleep: object,
    ) -> None:
        client = _PullStateClient([{"mergeable": False, "state": "open"}])
        builder = ForgejoPublicationPrefixBuilder(client)  # type: ignore[arg-type]

        with self.assertRaisesRegex(RuntimeError, "did not become mergeable"):
            builder._wait_for_pull_mergeable(
                "owner",
                "repo",
                2,
                attempts=2,
                interval_seconds=0.01,
            )

        self.assertEqual(client.calls, 2)
        self.assertEqual(sleep.call_count, 1)  # type: ignore[attr-defined]
