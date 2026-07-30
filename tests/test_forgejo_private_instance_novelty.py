from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.verify_forgejo_instance_novelty import find_overlaps


class ForgejoPrivateInstanceNoveltyTests(unittest.TestCase):
    def test_reports_field_and_path_without_echoing_private_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "public.txt"
            path.write_text("repository=private-repository", encoding="utf-8")
            instance = {
                field: f"private-{field}"
                for field in (
                    "scenario_id",
                    "owner",
                    "repository",
                    "package_name",
                    "package_slug",
                    "build_id",
                    "base_branch",
                    "feature_branch",
                    "protected_branch",
                    "release_tag",
                    "protected_release_tag",
                    "manifest_path",
                    "protected_file_path",
                    "release_title",
                    "release_body",
                    "milestone_title",
                    "target_issue_title",
                    "protected_pull_title",
                    "protected_issue_title",
                    "protected_release_title",
                    "coordinator_consumer",
                    "provenance_consumer",
                )
            }

            overlaps = find_overlaps(instance, [path])

        self.assertEqual(
            overlaps,
            [{"field": "repository", "path": path.as_posix()}],
        )
        self.assertNotIn("private-repository", repr(overlaps))

    def test_accepts_identity_disjoint_from_public_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "public.txt"
            path.write_text("unrelated public task", encoding="utf-8")
            instance = {
                field: f"private-{field}"
                for field in (
                    "scenario_id",
                    "owner",
                    "repository",
                    "package_name",
                    "package_slug",
                    "build_id",
                    "base_branch",
                    "feature_branch",
                    "protected_branch",
                    "release_tag",
                    "protected_release_tag",
                    "manifest_path",
                    "protected_file_path",
                    "release_title",
                    "release_body",
                    "milestone_title",
                    "target_issue_title",
                    "protected_pull_title",
                    "protected_issue_title",
                    "protected_release_title",
                    "coordinator_consumer",
                    "provenance_consumer",
                )
            }

            self.assertEqual(find_overlaps(instance, [path]), [])


if __name__ == "__main__":
    unittest.main()
