from __future__ import annotations

import unittest
from dataclasses import replace

from aftermath_bench.integrations.forgejo_publication_instance import (
    DEFAULT_FORGEJO_PUBLICATION_INSTANCE,
    publication_blueprint,
)
from aftermath_bench.integrations.forgejo_publication_prefix import (
    ForgejoPublicationPrefixBuilder,
)
from scripts.build_forgejo_publication_admission import _observed_graph


class ForgejoPublicationInstanceTests(unittest.TestCase):
    def _alternate(self):
        return replace(
            DEFAULT_FORGEJO_PUBLICATION_INSTANCE,
            scenario_id="forgejo-release-publication-hidden-901",
            owner="northstar",
            repository="telemetry-delivery",
            package_name="Telemetry Gateway",
            package_slug="telemetry-gateway",
            version="4.8.0",
            platform="linux_arm64",
            build_id="approved-telemetry-480",
            base_branch="release/4.8",
            feature_branch="publish/4.8",
            protected_branch="work/4.9",
            release_tag="v4.8.0",
            protected_release_tag="v4.7.2",
            manifest_path="ops/approved-artifacts.json",
            protected_file_path="notes/future.md",
            branch_protection_rule="release/**",
            release_title="Telemetry Gateway 4.8",
            release_body="Approved production bundle.",
            milestone_title="Telemetry Gateway 4.8 rollout",
            target_issue_title="Publish the gateway bundle",
            protected_pull_title="Prepare 4.9 notes",
            protected_issue_title="Plan the 4.9 rollout",
            protected_release_title="Telemetry Gateway 4.7.2",
            coordinator_consumer="deployment-controller",
            provenance_consumer="attestation-ledger",
        )

    def test_alternate_instance_changes_every_task_identifier(self) -> None:
        instance = self._alternate()
        instance.validate()
        blueprint = publication_blueprint(
            instance,
            instance_id="candidate-901",
            benchmark_split="hidden_test",
            hidden_test_eligible=True,
        )
        assets = ForgejoPublicationPrefixBuilder(
            object(), instance  # type: ignore[arg-type]
        )._asset_sources()
        serialized = repr((blueprint, assets))

        self.assertEqual(blueprint["scenario_id"], instance.scenario_id)
        self.assertEqual(blueprint["domain_id"], "forgejo")
        self.assertEqual(blueprint["instance_id"], "candidate-901")
        self.assertEqual(
            blueprint["instance_spec_sha256"], instance.sha256
        )
        self.assertNotIn("aftermath-agent_2026.08.0", serialized)
        self.assertNotIn("artifact-publication", serialized)
        self.assertNotIn("release/publication-manifest.json", serialized)
        self.assertEqual(
            {asset["role"] for asset in assets},
            {"binary", "checksum", "sbom"},
        )
        variants = blueprint["matched_variants"]
        self.assertEqual(len(variants), 8)
        self.assertEqual(
            {
                item["boundary_class_id"]
                for item in variants
            },
            {
                "no_primary_effect",
                "downstream_effect_missing",
                "downstream_effect_pending_or_accepted",
            },
        )
        self.assertEqual(
            len(
                {
                    item["recovery_signature_class"]
                    for item in variants
                }
            ),
            3,
        )

    def test_public_dev_blueprint_is_not_hidden_eligible(self) -> None:
        blueprint = publication_blueprint(
            self._alternate(),
            instance_id="dev-002",
            benchmark_split="public_dev",
            hidden_test_eligible=False,
        )

        self.assertEqual(blueprint["benchmark_split"], "public_dev")
        self.assertFalse(
            blueprint["evaluation_status"]["hidden_test_eligible"]
        )

    def test_split_and_hidden_eligibility_must_agree(self) -> None:
        with self.assertRaisesRegex(ValueError, "must agree"):
            publication_blueprint(
                self._alternate(),
                instance_id="test-001",
                benchmark_split="hidden_test",
                hidden_test_eligible=False,
            )

    def test_observed_graph_uses_instance_paths_and_rules(self) -> None:
        instance = self._alternate()
        assets = ForgejoPublicationPrefixBuilder(
            object(), instance  # type: ignore[arg-type]
        )._asset_sources()
        prefix = {
            "scenario_id": instance.scenario_id,
            "instance_spec_sha256": instance.sha256,
            "repository": instance.repository,
            "base_branch": instance.base_branch,
            "feature_branch": instance.feature_branch,
            "protected_branch": instance.protected_branch,
            "manifest_path": instance.manifest_path,
            "branch_protection_rule": instance.branch_protection_rule,
            "pull_request_index": 17,
            "linked_issue_index": 14,
            "milestone_id": 6,
            "protected_pull_request_index": 18,
            "protected_issue_index": 19,
            "coordinator_hook_id": 31,
            "provenance_hook_id": 32,
            "release_tag": instance.release_tag,
            "protected_release_tag": instance.protected_release_tag,
            "protected_asset_name": instance.protected_asset_name,
            "expected_assets": [
                {
                    "role": asset["role"],
                    "name": asset["name"],
                    "source_path": asset["source_path"],
                }
                for asset in assets
            ],
        }

        graph = _observed_graph(prefix)
        serialized = repr(graph)

        self.assertEqual(graph["scenario_id"], instance.scenario_id)
        self.assertIn(instance.manifest_path, serialized)
        self.assertIn(instance.protected_branch, serialized)
        self.assertIn(instance.branch_protection_rule, serialized)
        self.assertNotIn("work/next-release", serialized)
        self.assertNotIn("release/publication-manifest.json", serialized)

    def test_instance_hash_changes_for_one_fact(self) -> None:
        instance = self._alternate()
        changed = replace(instance, manifest_path="ops/release-set.json")

        self.assertNotEqual(instance.sha256, changed.sha256)


if __name__ == "__main__":
    unittest.main()
