from __future__ import annotations

import unittest
from typing import Any

from scripts.run_forgejo_package_provenance_baseline import BASELINES, execute


class _Environment:
    def __init__(
        self,
        *,
        files: tuple[str, ...],
        release_exists: bool,
        failed_deliveries: bool,
    ) -> None:
        self.files = list(files)
        self.release_exists = release_exists
        self.histories = {
            11: (
                [{"uuid": "c-failed", "status": "failed"}] if failed_deliveries else []
            ),
            12: (
                [{"uuid": "p-failed", "status": "failed"}] if failed_deliveries else []
            ),
        }
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def invoke(self, tool: str, **arguments: Any) -> dict[str, Any]:
        self.calls.append((tool, arguments))
        if tool == "list_package_files":
            return {"ok": True, "result": [{"name": item} for item in self.files]}
        if tool == "upload_package_file_from_repository":
            self.files.append(str(arguments["filename"]))
            return {"ok": True, "result": {}}
        if tool == "get_webhook_history":
            return {
                "ok": True,
                "result": list(self.histories[int(arguments["hook_id"])]),
            }
        if tool == "list_releases":
            return {
                "ok": True,
                "result": ([{"tag_name": "v2.4.1"}] if self.release_exists else []),
            }
        if tool == "create_package_index_release":
            self.release_exists = True
            return {"ok": True, "result": {}}
        return {"ok": True, "result": {}}


def _prefix() -> dict[str, Any]:
    return {
        "package_name": "orbitctl",
        "package_version": "2.4.1",
        "base_branch": "release-2.4",
        "package_index_release_tag": "v2.4.1",
        "package_index_release_title": "Orbit Control CLI 2.4.1",
        "package_index_release_body": "approved package index",
        "coordinator_hook_id": 11,
        "provenance_hook_id": 12,
        "milestone_id": 3,
        "tracking_issue_indexes": [5, 6, 7],
        "expected_package_files": [
            {"name": "binary", "source_path": "dist/binary"},
            {"name": "checksum", "source_path": "dist/checksum"},
            {"name": "sbom", "source_path": "dist/sbom"},
            {"name": "signature", "source_path": "dist/signature"},
        ],
    }


class ForgejoPackageProvenanceBaselineTests(unittest.TestCase):
    def test_adaptive_inventory_baseline_is_part_of_the_hard_gate(self) -> None:
        self.assertIn("inventory_diff_completion", BASELINES)

    def test_adaptive_baseline_completes_only_missing_inventory(self) -> None:
        environment = _Environment(
            files=("binary", "checksum"),
            release_exists=False,
            failed_deliveries=False,
        )
        execute("inventory_diff_completion", environment, _prefix())
        uploads = [
            arguments["filename"]
            for tool, arguments in environment.calls
            if tool == "upload_package_file_from_repository"
        ]
        self.assertEqual(uploads, ["sbom", "signature"])
        self.assertEqual(
            sum(
                tool == "create_package_index_release" for tool, _ in environment.calls
            ),
            1,
        )

    def test_adaptive_baseline_replays_only_failed_existing_deliveries(self) -> None:
        environment = _Environment(
            files=("binary", "checksum", "sbom", "signature"),
            release_exists=True,
            failed_deliveries=True,
        )
        execute("inventory_diff_completion", environment, _prefix())
        self.assertFalse(
            any(
                tool
                in {
                    "upload_package_file_from_repository",
                    "create_package_index_release",
                }
                for tool, _ in environment.calls
            )
        )
        self.assertEqual(
            sum(tool == "replay_webhook" for tool, _ in environment.calls),
            2,
        )


if __name__ == "__main__":
    unittest.main()
