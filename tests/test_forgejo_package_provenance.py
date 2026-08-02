from __future__ import annotations

import unittest

from aftermath_bench.integrations.forgejo_package_provenance_faults import (
    PACKAGE_PROVENANCE_VARIANTS,
)
from aftermath_bench.integrations.forgejo_package_provenance_recovery import (
    evaluate_forgejo_package_provenance_recovery,
)
from aftermath_bench.native_forgejo_package_provenance_family import (
    FORGEJO_PACKAGE_PROVENANCE_FAMILY,
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
        "coordinator_hook_id": 11,
        "provenance_hook_id": 12,
    }


def _evidence() -> dict:
    return {
        "target_pull": {"merged": True, "state": "closed"},
        "linked_issue": {"state": "closed"},
        "release_milestone": {"state": "closed"},
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
        self.assertIn("upload_package_file_from_repository", names)
        self.assertNotIn("repair_package", names)
        self.assertNotIn("get_global_state", names)

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

    def test_complete_native_state_passes(self) -> None:
        report = evaluate_forgejo_package_provenance_recovery(
            _evidence(),
            prefix=_prefix(),
        )
        self.assertTrue(report.passed, report.failures)

    def test_missing_signature_is_a_repair_completeness_failure(self) -> None:
        evidence = _evidence()
        evidence["target_package_files"] = evidence[
            "target_package_files"
        ][:-1]
        report = evaluate_forgejo_package_provenance_recovery(
            evidence,
            prefix=_prefix(),
        )
        self.assertFalse(report.passed)
        self.assertFalse(report.components["repair_completeness"])
        self.assertTrue(report.components["preservation"])


if __name__ == "__main__":
    unittest.main()
