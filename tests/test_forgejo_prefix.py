from __future__ import annotations

import unittest
from unittest.mock import Mock

from aftermath_bench.integrations.forgejo_prefix import (
    ForgejoReleasePrefixBuilder,
)


class ForgejoPrefixTest(unittest.TestCase):
    def test_prefix_is_built_only_through_public_native_operations(self) -> None:
        client = Mock()
        client.create_repository.return_value = {
            "name": "release-control",
            "owner": {"login": "aftermath"},
        }
        client.create_milestone.return_value = {"id": 1}
        client.create_issue.side_effect = [
            {"number": 1},
            {"number": 4},
        ]
        client.create_branch.side_effect = [
            {"name": "release/2026.07"},
            {"name": "fix/customer-export-timeout"},
            {"name": "hotfix/legacy-auth-header"},
        ]
        client.edit_repository.return_value = {
            "default_branch": "release/2026.07"
        }
        client.create_file.side_effect = [
            {"commit": {"sha": "feature"}},
            {"commit": {"sha": "hotfix"}},
        ]
        client.create_pull_request.side_effect = [
            {"number": 2},
            {"number": 3},
        ]
        client.create_release.return_value = {"tag_name": "v2026.06.4"}
        client.create_branch_protection.return_value = {
            "rule_name": "release/*"
        }
        client.create_hook.return_value = {"id": 9}
        prefix = ForgejoReleasePrefixBuilder(client).build()
        self.assertEqual(prefix.pull_request_index, 2)
        self.assertEqual(prefix.protected_pull_request_index, 3)
        self.assertEqual(prefix.protected_issue_index, 4)
        self.assertEqual(prefix.webhook_id, 9)
        self.assertEqual(len(prefix.trace), 15)
        self.assertEqual(
            [entry["tool"] for entry in prefix.trace].count(
                "create_pull_request"
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
