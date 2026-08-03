from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.integrations.forgejo_migration_instance import (
    ForgejoMigrationInstanceSpec,
    migration_blueprint,
)
from scripts.verify_forgejo_migration_instance_novelty import (
    find_overlaps,
    novelty_scan_paths,
)


class ForgejoMigrationInstanceNoveltyTests(unittest.TestCase):
    def test_bound_instance_and_blueprint_are_the_only_exclusions(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            instance = self._instance()
            spec_path = root / "instance.json"
            blueprint_path = root / "scenario.json"
            other = root / "other.txt"
            self._write(spec_path, instance.as_dict())
            self._write(
                blueprint_path,
                migration_blueprint(
                    instance,
                    instance_id="dev-001",
                    benchmark_split="public_dev",
                ),
            )
            other.write_text("unrelated material", encoding="utf-8")
            selected = novelty_scan_paths(
                [spec_path, blueprint_path, other],
                instance_spec_path=spec_path,
                instance=instance,
                bound_blueprint_path=blueprint_path,
            )
            self.assertEqual(selected, [other])
            self.assertEqual(find_overlaps(instance.as_dict(), selected), [])

    def test_identity_overlap_and_spoofed_blueprint_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            instance = self._instance()
            leaked = root / "leaked.txt"
            leaked.write_text(instance.repository, encoding="utf-8")
            self.assertEqual(
                find_overlaps(instance.as_dict(), [leaked]),
                [{"field": "repository", "path": leaked.as_posix()}],
            )
            spec_path = root / "instance.json"
            blueprint_path = root / "scenario.json"
            self._write(spec_path, instance.as_dict())
            spoofed = migration_blueprint(
                instance,
                instance_id="dev-001",
                benchmark_split="public_dev",
            )
            spoofed["instance_spec_sha256"] = "b" * 64
            self._write(blueprint_path, spoofed)
            with self.assertRaisesRegex(ValueError, "does not match"):
                novelty_scan_paths(
                    [spec_path, blueprint_path],
                    instance_spec_path=spec_path,
                    instance=instance,
                    bound_blueprint_path=blueprint_path,
                )

    @staticmethod
    def _instance() -> ForgejoMigrationInstanceSpec:
        return ForgejoMigrationInstanceSpec(
            scenario_id="forgejo-migration-public-dev-test",
            owner="novel-owner",
            repository="novel-deployment-repository",
            version="9.1.0",
            prior_version="9.0.4",
            migration_id="2026-08-novel-migration",
            schema_hash="sha256:11111111111111111111111111111111",
            artifact_digest="sha256:22222222222222222222222222222222",
            workflow_path=".forgejo/workflows/novel-deploy.yml",
            migration_path="migrations/novel.sql",
            artifact_manifest_path="deploy/novel.json",
            production_environment="novel-production",
            protected_environment="novel-staging",
            release_tag="v9.1.0",
            protected_release_tag="v9.0.4",
            milestone_title="Novel production rollout milestone",
            change_issue_title="Deploy novel approved migration",
            protected_issue_title="Plan the novel next rollout",
        )

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
