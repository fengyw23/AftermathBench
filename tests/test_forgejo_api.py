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

    def test_release_attachment_uses_native_raw_upload_endpoint(self) -> None:
        with patch(
            "urllib.request.urlopen",
            return_value=_Response({"id": 11, "name": "bundle.tgz"}),
        ) as opener:
            result = ForgejoAPI(
                base_url="http://forgejo.invalid/api/v1",
                token="secret-token",
            ).create_release_attachment(
                "aftermath",
                "artifact-publication",
                9,
                name="bundle.tgz",
                content=b"approved-bundle",
            )
        request = opener.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://forgejo.invalid/api/v1/repos/aftermath/"
            "artifact-publication/releases/9/assets?name=bundle.tgz",
        )
        self.assertEqual(request.data, b"approved-bundle")
        self.assertEqual(result["id"], 11)

    def test_generic_package_upload_uses_native_registry_route(self) -> None:
        with patch(
            "urllib.request.urlopen",
            return_value=_Response({}),
        ) as opener:
            ForgejoAPI(
                base_url="http://forgejo.invalid/api/v1",
                token="secret-token",
            ).upload_generic_package_file(
                "aftermath",
                name="recovery-agent",
                version="2.4.1",
                filename="recovery-agent.sig",
                content=b"signed-provenance",
            )
        request = opener.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://forgejo.invalid/api/packages/aftermath/generic/"
            "recovery-agent/2.4.1/recovery-agent.sig",
        )
        self.assertEqual(request.method, "PUT")
        self.assertEqual(request.data, b"signed-provenance")
        self.assertEqual(request.headers["Authorization"], "token secret-token")

    def test_package_metadata_uses_v1_api(self) -> None:
        with patch(
            "urllib.request.urlopen",
            return_value=_Response([{"name": "recovery-agent"}]),
        ) as opener:
            result = ForgejoAPI(
                base_url="http://forgejo.invalid/api/v1",
                token="secret-token",
            ).list_packages(
                "aftermath",
                package_type="generic",
                query="recovery-agent",
            )
        request = opener.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://forgejo.invalid/api/v1/packages/aftermath?"
            "type=generic&limit=50&q=recovery-agent",
        )
        self.assertEqual(result[0]["name"], "recovery-agent")

    def test_workflow_dispatch_requests_native_run_information(self) -> None:
        with patch(
            "urllib.request.urlopen",
            return_value=_Response({"id": 71, "run_number": 5, "jobs": ["deploy"]}),
        ) as opener:
            result = ForgejoAPI(
                base_url="http://forgejo.invalid/api/v1",
                token="secret-token",
            ).dispatch_workflow(
                "aftermath",
                "migration-service",
                workflow="deploy production.yml",
                ref="refs/heads/release/2026.09",
                inputs={"schema_epoch": "12"},
            )
        request = opener.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://forgejo.invalid/api/v1/repos/aftermath/migration-service/"
            "actions/workflows/deploy%20production.yml/dispatches",
        )
        self.assertEqual(
            json.loads(request.data),
            {
                "ref": "refs/heads/release/2026.09",
                "inputs": {"schema_epoch": "12"},
                "return_run_info": True,
            },
        )
        self.assertEqual(result["id"], 71)

    def test_workflow_dispatch_normalizes_repository_relative_path(self) -> None:
        with patch(
            "urllib.request.urlopen",
            return_value=_Response({"id": 72, "run_number": 6}),
        ) as opener:
            ForgejoAPI(
                base_url="http://forgejo.invalid/api/v1",
                token="secret-token",
            ).dispatch_workflow(
                "aftermath",
                "migration-service",
                workflow=".forgejo/workflows/deploy-production.yml",
                ref="main",
            )
        request = opener.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://forgejo.invalid/api/v1/repos/aftermath/migration-service/"
            "actions/workflows/deploy-production.yml/dispatches",
        )

    def test_action_run_and_artifact_reads_use_native_endpoints(self) -> None:
        responses = [
            _Response({"workflow_runs": [{"id": 71}], "total_count": 1}),
            _Response([{"id": 9, "name": "deployment-record"}]),
        ]
        with patch("urllib.request.urlopen", side_effect=responses) as opener:
            client = ForgejoAPI(
                base_url="http://forgejo.invalid/api/v1",
                token="secret-token",
            )
            runs = client.list_action_runs(
                "aftermath",
                "migration-service",
                workflow="deploy.yml",
                ref="refs/heads/main",
            )
            artifacts = client.list_action_run_artifacts(
                "aftermath", "migration-service", 71
            )
        self.assertEqual(runs[0]["id"], 71)
        self.assertEqual(artifacts[0]["name"], "deployment-record")
        self.assertIn("workflow_id=deploy.yml", opener.call_args_list[0].args[0].full_url)
        self.assertIn("ref=refs%2Fheads%2Fmain", opener.call_args_list[0].args[0].full_url)


if __name__ == "__main__":
    unittest.main()
