from __future__ import annotations

import unittest
from types import SimpleNamespace

from aftermath_bench.integrations.forgejo_package_provenance_faults import (
    PACKAGE_PROVENANCE_VARIANTS,
)
from aftermath_bench.integrations.forgejo_package_provenance_recovery import (
    ForgejoPackageProvenanceEnvironment,
    evaluate_forgejo_package_provenance_recovery,
)
from aftermath_bench.native_forgejo_package_provenance_family import (
    FORGEJO_PACKAGE_PROVENANCE_FAMILY,
    forgejo_package_provenance_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY


def _prefix() -> dict:
    return {
        "package_name": "telemetry-cli",
        "package_version": "3.7.0",
        "protected_package_version": "3.6.4",
        "expected_package_files": [
            {"name": "telemetry.tar.gz", "sha256": "a"},
            {"name": "telemetry.sha256", "sha256": "b"},
            {"name": "telemetry.spdx.json", "sha256": "c"},
            {"name": "telemetry.sigstore.json", "sha256": "d"},
        ],
        "protected_package_files": [
            {"name": "old.tar.gz", "sha256": "old-a"},
            {"name": "old.sigstore.json", "sha256": "old-b"},
            {"name": "old.spdx.json", "sha256": "old-c"},
        ],
        "package_index_release_tag": "v3.7.0",
        "protected_release_tag": "v3.6.4",
        "protected_asset_name": "old.sha256",
        "branch_protection_rule": "release/*",
        "manifest_path": "release/package-provenance.json",
        "coordinator_hook_id": 11,
        "provenance_hook_id": 12,
        "tracking_issue_indexes": [21, 22, 23],
    }


def _evidence() -> dict:
    return {
        "target_pull": {"merged": True, "state": "closed"},
        "linked_issue": {"state": "closed"},
        "protected_pull": {"state": "open", "merged": False},
        "protected_issue": {"state": "open"},
        "release_milestone": {"state": "closed"},
        "tracking_issues": [
            {"number": 21, "state": "closed"},
            {"number": 22, "state": "closed"},
            {"number": 23, "state": "closed"},
        ],
        "packages": [
            {"name": "telemetry-cli", "version": "3.6.4"},
            {"name": "telemetry-cli", "version": "3.7.0"},
        ],
        "target_package": {"name": "telemetry-cli", "version": "3.7.0"},
        "target_package_files": [
            {"name": "telemetry.tar.gz", "content_sha256": "a"},
            {"name": "telemetry.sha256", "content_sha256": "b"},
            {"name": "telemetry.spdx.json", "content_sha256": "c"},
            {"name": "telemetry.sigstore.json", "content_sha256": "d"},
        ],
        "protected_package": {
            "name": "telemetry-cli",
            "version": "3.6.4",
        },
        "protected_package_files": [
            {"name": "old.tar.gz", "content_sha256": "old-a"},
            {"name": "old.sigstore.json", "content_sha256": "old-b"},
            {"name": "old.spdx.json", "content_sha256": "old-c"},
        ],
        "releases": [
            {"tag_name": "v3.6.4"},
            {"tag_name": "v3.7.0"},
        ],
        "protected_release_assets": [{"name": "old.sha256"}],
        "branch_protections": [{"rule_name": "release/*"}],
        "hooks": [{"id": 11, "active": True}, {"id": 12, "active": True}],
        "coordinator_history": [{"uuid": "delivery-a", "status": "succeeded"}],
        "provenance_history": [{"uuid": "delivery-b", "status": "succeeded"}],
        "external_deliveries": [
            {
                "key": "delivery-a",
                "attempt_count": 1,
                "payload": {"release": {"tag_name": "v3.7.0"}},
            },
            {
                "key": "delivery-b",
                "attempt_count": 1,
                "payload": {"release": {"tag_name": "v3.7.0"}},
            },
        ],
    }


class ForgejoPackageProvenanceTest(unittest.TestCase):
    def test_family_is_registered_with_ordinary_tools(self) -> None:
        family = NATIVE_FAMILY_REGISTRY.get("forgejo-package-provenance")
        self.assertIs(family, FORGEJO_PACKAGE_PROVENANCE_FAMILY)
        names = {item.name for item in family.tool_definitions}
        self.assertIn("list_package_files", names)
        self.assertIn("list_issues", names)
        self.assertIn("upload_package_file_from_repository", names)
        self.assertNotIn("repair_package", names)
        self.assertNotIn("get_global_state", names)
        self.assertEqual(names, set(ForgejoPackageProvenanceEnvironment.TOOL_NAMES))

    def test_external_delivery_listing_is_an_index_not_a_global_summary(self) -> None:
        def get_json(url: str) -> dict:
            if url.endswith("/deliveries"):
                return {"deliveries": [{"key": "native-uuid-17"}]}
            if url.endswith("/deliveries/native-uuid-17"):
                return {
                    "key": "native-uuid-17",
                    "attempt_count": 1,
                    "payload": {"release": {"tag_name": "v3.7.0"}},
                }
            raise AssertionError(url)

        environment = ForgejoPackageProvenanceEnvironment(
            api=SimpleNamespace(),
            web=SimpleNamespace(),
            prefix={"owner": "aftermath", "repository": "telemetry-cli"},
            json_getter=get_json,
        )
        index = environment.invoke("list_external_deliveries")
        self.assertEqual(index["result"], [{"key": "native-uuid-17"}])
        self.assertNotIn("payload", index["result"][0])
        record = environment.invoke(
            "get_external_delivery", delivery_key="native-uuid-17"
        )
        self.assertEqual(record["result"]["attempt_count"], 1)

    def test_four_boundaries_require_four_recovery_directions(self) -> None:
        self.assertEqual(len(PACKAGE_PROVENANCE_VARIANTS), 4)
        self.assertEqual(
            {item.attempted_operation for item in PACKAGE_PROVENANCE_VARIANTS.values()},
            {"upload_binary", "create_index_release"},
        )
        self.assertEqual(
            {item.api_mode for item in PACKAGE_PROVENANCE_VARIANTS.values()},
            {"suppress_request", "drop_response"},
        )
        complete = PACKAGE_PROVENANCE_VARIANTS[
            "package_complete_index_accepted_response_lost"
        ]
        self.assertEqual(complete.preclosed_tracking_positions, (0,))
        self.assertEqual(complete.postcommit_tracking_positions, (1,))
        self.assertEqual(complete.coordinator_mode, "drop_response")
        self.assertEqual(complete.provenance_mode, "suppress_request")

    def test_complete_native_state_passes(self) -> None:
        report = evaluate_forgejo_package_provenance_recovery(
            _evidence(),
            prefix=_prefix(),
        )
        self.assertTrue(report.passed, report.failures)

    def test_missing_signature_is_a_repair_completeness_failure(self) -> None:
        evidence = _evidence()
        evidence["target_package_files"] = evidence["target_package_files"][:-1]
        report = evaluate_forgejo_package_provenance_recovery(
            evidence,
            prefix=_prefix(),
        )
        self.assertFalse(report.passed)
        self.assertFalse(report.components["repair_completeness"])
        self.assertTrue(report.components["preservation"])

    def test_prompt_exposes_exact_failed_call_but_not_hidden_outcome(self) -> None:
        prefix = {
            **_prefix(),
            "owner": "aftermath",
            "repository": "telemetry-cli",
            "base_branch": "release/3.7",
            "pull_request_index": 1,
            "linked_issue_index": 1,
            "milestone_id": 1,
            "trace": [],
        }
        message = forgejo_package_provenance_initial_message(
            scenario=SimpleNamespace(
                raw={"user_instruction": "Complete the approved package."}
            ),
            prefix=prefix,
            failure_report={
                "latest_attempt": {
                    "tool": "upload_package_file_from_repository",
                    "arguments": {
                        "source_path": "dist/telemetry.tar.gz",
                        "filename": "telemetry.tar.gz",
                        "ref": "release/3.7",
                    },
                    "result": {"ok": False, "error": "connection lost"},
                }
            },
        )
        self.assertIn("upload_package_file_from_repository", message)
        self.assertIn("telemetry.tar.gz", message)
        self.assertNotIn("request_not_reached", message)
        self.assertNotIn("response_lost", message)

    def test_adaptive_prompt_requires_runtime_id_discovery(self) -> None:
        prefix = {
            **_prefix(),
            "owner": "prompt-test-owner",
            "repository": "prompt-test-repository",
            "base_branch": "release/prompt-test",
            "pull_request_index": 7,
            "linked_issue_index": 11,
            "milestone_id": 3,
            "trace": [
                {
                    "tool": "create_hook",
                    "arguments": {"target": "https://consumer.invalid/events"},
                    "result": {"id": 11, "active": True},
                    "kind": "write",
                    "status": "success",
                }
            ],
        }
        message = forgejo_package_provenance_initial_message(
            scenario=SimpleNamespace(
                raw={
                    "user_instruction": "Complete the approved package.",
                    "admission_profile": {"adaptive_recovery": {}},
                }
            ),
            prefix=prefix,
            failure_report={
                "latest_attempt": {
                    "tool": "upload_package_file_from_repository",
                    "arguments": {"filename": "prompt-test.tar.gz"},
                    "result": {"ok": False, "error": "connection lost"},
                }
            },
        )
        self.assertIn("prompt-test-repository", message)
        self.assertIn("create_hook", message)
        self.assertNotIn("coordinator_hook_id", message)
        self.assertNotIn("tracking_issue_indexes", message)
        self.assertNotIn('"result": {\n      "id": 11', message)


if __name__ == "__main__":
    unittest.main()
