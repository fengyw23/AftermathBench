from __future__ import annotations

import unittest
from types import SimpleNamespace

from aftermath_bench.integrations.forgejo_package_provenance_faults import (
    PACKAGE_PROVENANCE_R2_VARIANTS,
    PACKAGE_PROVENANCE_VARIANTS,
)
from aftermath_bench.integrations.forgejo_package_provenance_recovery import (
    ForgejoPackageProvenanceEnvironment,
    evaluate_forgejo_package_provenance_recovery,
)
from aftermath_bench.native_forgejo_package_provenance_family import (
    FORGEJO_PACKAGE_PROVENANCE_FAMILY,
    diagnose_forgejo_package_provenance_trajectory,
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
        "package_index_release_title": "Telemetry CLI 3.7.0",
        "package_index_release_body": "approved package index",
        "base_branch": "release/3.7",
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
            {"id": 64, "tag_name": "v3.6.4"},
            {
                "id": 70,
                "tag_name": "v3.7.0",
                "name": "Telemetry CLI 3.7.0",
                "body": "approved package index",
                "target_commitish": "release/3.7",
            },
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
                "payload": {
                    "action": "published",
                    "release": {"tag_name": "v3.7.0"},
                },
            },
            {
                "key": "delivery-b",
                "attempt_count": 1,
                "payload": {
                    "action": "published",
                    "release": {"tag_name": "v3.7.0"},
                },
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
        self.assertIn("delete_package_version", names)
        self.assertIn("delete_release", names)
        self.assertIn("activate_webhook", names)
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
        partial = PACKAGE_PROVENANCE_VARIANTS["package_binary_committed_response_lost"]
        self.assertEqual(partial.preloaded_file_roles, ("checksum",))
        self.assertEqual(complete.preclosed_tracking_positions, (0,))
        self.assertEqual(complete.postcommit_tracking_positions, (1,))
        self.assertEqual(complete.coordinator_mode, "suppress_request")
        self.assertEqual(complete.provenance_mode, "suppress_request")

    def test_r2_contains_same_inventory_with_opposite_repair_polarity(self) -> None:
        valid = PACKAGE_PROVENANCE_R2_VARIANTS["r2_package_complete_index_missing"]
        corrupt = PACKAGE_PROVENANCE_R2_VARIANTS[
            "r2_package_corrupt_binary_index_missing"
        ]
        self.assertEqual(valid.preloaded_file_roles, corrupt.preloaded_file_roles)
        self.assertEqual(valid.attempted_operation, corrupt.attempted_operation)
        self.assertEqual(valid.api_mode, corrupt.api_mode)
        self.assertEqual(valid.coordinator_mode, "normal")
        self.assertEqual(valid.coordinator_mode, corrupt.coordinator_mode)
        self.assertEqual(
            valid.disabled_hook_roles,
            ("coordinator", "provenance"),
        )
        self.assertEqual(valid.disabled_hook_roles, corrupt.disabled_hook_roles)
        self.assertEqual(valid.corrupt_preloaded_file_roles, ())
        self.assertEqual(corrupt.corrupt_preloaded_file_roles, ("binary",))
        self.assertEqual(corrupt.advance_base_branch_file_roles, ("binary",))
        partial = PACKAGE_PROVENANCE_R2_VARIANTS[
            "r2_package_binary_committed_response_lost"
        ]
        self.assertEqual(partial.preloaded_file_roles, ("checksum", "sbom"))
        self.assertEqual(
            partial.disabled_hook_roles,
            ("coordinator", "provenance"),
        )

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

    def test_wrong_binary_with_identical_file_inventory_fails(self) -> None:
        evidence = _evidence()
        evidence["target_package_files"][0]["content_sha256"] = "wrong-binary"
        report = evaluate_forgejo_package_provenance_recovery(
            evidence,
            prefix=_prefix(),
        )
        self.assertFalse(report.passed)
        self.assertFalse(report.checks["package_file_contents_match_sources"])
        self.assertTrue(report.checks["exact_provenance_file_set"])

    def test_release_with_correct_tag_but_wrong_metadata_fails(self) -> None:
        evidence = _evidence()
        evidence["releases"][1]["target_commitish"] = "main"
        report = evaluate_forgejo_package_provenance_recovery(
            evidence,
            prefix=_prefix(),
        )
        self.assertFalse(report.passed)
        self.assertFalse(
            report.checks["package_index_release_matches_approved_metadata"]
        )
        self.assertTrue(report.checks["one_package_index_release"])

    def test_release_accepts_visible_branch_target_and_semantic_binding(self) -> None:
        prefix = _prefix()
        evidence = _evidence()
        evidence["releases"][1].update(
            {
                "name": "Telemetry CLI 3.7.0 supply-chain release",
                "target_commitish": prefix["base_branch"],
                "body": "\n".join(
                    [
                        f"Approved provenance: {prefix['manifest_path']}",
                        *(
                            f"{item['name']}: {item['sha256']}"
                            for item in prefix["expected_package_files"]
                        ),
                    ]
                ),
            }
        )
        report = evaluate_forgejo_package_provenance_recovery(
            evidence,
            prefix=prefix,
        )
        self.assertTrue(report.passed, report.failures)

    def test_release_body_prose_is_not_a_hidden_scoring_constraint(self) -> None:
        evidence = _evidence()
        evidence["releases"][1].update(
            {
                "name": "Telemetry CLI 3.7.0 release",
                "body": "Files verified.",
            }
        )
        report = evaluate_forgejo_package_provenance_recovery(
            evidence,
            prefix=_prefix(),
        )
        self.assertTrue(report.passed, report.failures)

    def test_release_title_must_identify_package_and_version(self) -> None:
        evidence = _evidence()
        evidence["releases"][1]["name"] = "Production release"
        report = evaluate_forgejo_package_provenance_recovery(
            evidence,
            prefix=_prefix(),
        )
        self.assertFalse(report.passed)
        self.assertFalse(
            report.checks["package_index_release_matches_approved_metadata"]
        )

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
            "approved_source_ref": "immutable-merge-commit-not-for-prompt",
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
        self.assertNotIn("approved_source_ref", message)
        self.assertNotIn("immutable-merge-commit-not-for-prompt", message)
        self.assertNotIn('"result": {\n      "id": 11', message)

    def test_r2_execution_control_names_the_opposite_package_scope(self) -> None:
        prefix = {
            **_prefix(),
            "owner": "aftermath",
            "repository": "telemetry-cli",
            "pull_request_index": 1,
            "linked_issue_index": 1,
            "milestone_id": 1,
            "trace": [],
        }
        scenario = SimpleNamespace(
            raw={"user_instruction": "Complete the approved package."}
        )
        ordinary = forgejo_package_provenance_initial_message(
            scenario=scenario,
            prefix=prefix,
            failure_report={
                "variant": "r2_package_corrupt_binary_index_missing",
                "latest_attempt": {"result": {"error": "connection lost"}},
            },
        )
        control = forgejo_package_provenance_initial_message(
            scenario=scenario,
            prefix=prefix,
            failure_report={
                "variant": "r2_package_corrupt_binary_index_missing",
                "latest_attempt": {"result": {"error": "connection lost"}},
            },
            execution_control=True,
        )
        self.assertNotIn("Delete the current target package version", ordinary)
        self.assertIn("Delete the current target package version", control)
        self.assertIn("approved Pull Request merge commit", control)
        self.assertNotIn("Retain the prior target package version", control)

    def test_r2_same_inventory_failure_requires_the_approval_hash_join(self) -> None:
        ordinary_inventory_queries = [
            "list_packages",
            "list_releases",
            "list_hooks",
            "list_external_deliveries",
            "get_webhook_history",
            "get_webhook_history",
        ]
        failed = SimpleNamespace(
            passed=False,
            components={
                "preservation": False,
                "protocol_safety": True,
                "goal_completion": False,
            },
        )

        def diagnose(extra: list[str]) -> dict:
            return diagnose_forgejo_package_provenance_trajectory(
                turns=[
                    {
                        "tool_calls": [
                            {"name": name, "arguments": {}}
                            for name in ordinary_inventory_queries + extra
                        ]
                    }
                ],
                evaluation=failed,
                failure_report={
                    "variant": "r2_package_corrupt_binary_index_missing"
                },
                prefix={},
            )

        missing_join = diagnose([])
        self.assertEqual(missing_join["primary_error"], "investigation_failure")
        self.assertFalse(missing_join["provenance_join_complete"])

        joined = diagnose(
            ["get_pull_request", "get_repository_file", "get_package_file"]
        )
        self.assertTrue(joined["provenance_join_complete"])
        self.assertEqual(joined["primary_error"], "scope_failure")


if __name__ == "__main__":
    unittest.main()
