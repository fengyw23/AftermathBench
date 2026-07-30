from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.integrations.forgejo_publication_instance import (
    ForgejoPublicationInstanceSpec,
)
from scripts.verify_forgejo_instance_novelty import (
    find_overlaps,
    novelty_scan_paths,
)


class ForgejoPrivateInstanceNoveltyTests(unittest.TestCase):
    @staticmethod
    def _instance() -> ForgejoPublicationInstanceSpec:
        return ForgejoPublicationInstanceSpec.from_dict(
            {
                "scenario_id": "forgejo-public-dev-novelty-test",
                "owner": "novel-owner",
                "repository": "novel-repository",
                "package_name": "Novel Package",
                "package_slug": "novel-package",
                "version": "9.8.7",
                "platform": "linux_arm64",
                "build_id": "novel-build-987",
                "base_branch": "release/9.8",
                "feature_branch": "publish/9.8.7",
                "protected_branch": "work/9.9",
                "release_tag": "v9.8.7",
                "protected_release_tag": "v9.7.6",
                "manifest_path": "ops/novel-manifest.json",
                "protected_file_path": "docs/novel-protected.md",
                "branch_protection_rule": "release/**",
                "release_title": "Novel Package 9.8.7",
                "release_body": "Publish the novel approved bundle.",
                "milestone_title": "Novel Package rollout",
                "target_issue_title": "Publish novel package",
                "protected_pull_title": "Prepare future novel release",
                "protected_issue_title": "Plan future novel rollout",
                "protected_release_title": "Novel Package 9.7.6",
                "coordinator_consumer": "novel-coordinator",
                "provenance_consumer": "novel-provenance",
                "coordinator_target": (
                    "http://coordinator.invalid/webhooks/events"
                ),
                "provenance_target": (
                    "http://provenance.invalid/webhooks/events"
                ),
            }
        )

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

    def test_excludes_spec_and_strictly_bound_blueprint(self) -> None:
        instance = self._instance()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = root / "instance.json"
            blueprint = root / "blueprint.json"
            other = root / "other.txt"
            spec.write_text(
                json.dumps(instance.as_dict()),
                encoding="utf-8",
            )
            blueprint.write_text(
                json.dumps(
                    {
                        "scenario_id": instance.scenario_id,
                        "instance_spec_sha256": instance.sha256,
                        "repository": instance.repository,
                    }
                ),
                encoding="utf-8",
            )
            other.write_text("unrelated corpus", encoding="utf-8")

            paths = novelty_scan_paths(
                [spec, blueprint, other],
                instance_spec_path=spec,
                instance=instance,
                bound_blueprint_path=blueprint,
            )

            self.assertEqual(paths, [other])
            self.assertEqual(find_overlaps(instance.as_dict(), paths), [])

    def test_rejects_unparseable_or_incorrectly_bound_blueprint(self) -> None:
        instance = self._instance()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = root / "instance.json"
            spec.write_text(
                json.dumps(instance.as_dict()),
                encoding="utf-8",
            )
            cases = {
                "unparseable": "{",
                "wrong-scenario": json.dumps(
                    {
                        "scenario_id": "different-scenario",
                        "instance_spec_sha256": instance.sha256,
                    }
                ),
                "wrong-hash": json.dumps(
                    {
                        "scenario_id": instance.scenario_id,
                        "instance_spec_sha256": "0" * 64,
                    }
                ),
            }
            for name, content in cases.items():
                with self.subTest(name=name):
                    blueprint = root / f"{name}.json"
                    blueprint.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        novelty_scan_paths(
                            [spec, blueprint],
                            instance_spec_path=spec,
                            instance=instance,
                            bound_blueprint_path=blueprint,
                        )

    def test_bound_blueprint_does_not_hide_other_corpus_overlap(self) -> None:
        instance = self._instance()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = root / "instance.json"
            blueprint = root / "blueprint.json"
            public = root / "public.txt"
            spec.write_text(
                json.dumps(instance.as_dict()),
                encoding="utf-8",
            )
            blueprint.write_text(
                json.dumps(
                    {
                        "scenario_id": instance.scenario_id,
                        "instance_spec_sha256": instance.sha256,
                    }
                ),
                encoding="utf-8",
            )
            public.write_text(
                f"repository={instance.repository}",
                encoding="utf-8",
            )

            paths = novelty_scan_paths(
                [spec, blueprint, public],
                instance_spec_path=spec,
                instance=instance,
                bound_blueprint_path=blueprint,
            )

            self.assertEqual(
                find_overlaps(instance.as_dict(), paths),
                [
                    {
                        "field": "repository",
                        "path": public.as_posix(),
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
