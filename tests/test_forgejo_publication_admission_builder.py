from __future__ import annotations

import unittest

from aftermath_bench.evidence_replay import replay_graph
from aftermath_bench.integrations.forgejo_publication_faults import (
    PUBLICATION_VARIANTS,
)
from scripts.build_forgejo_publication_admission import _observed_graph


def _prefix() -> dict:
    return {
        "scenario_id": "forgejo-release-publication-test",
        "instance_spec_sha256": "test-spec-sha",
        "repository": "artifact-publication",
        "base_branch": "release/2026.08",
        "feature_branch": "release/2026.08-publication",
        "protected_branch": "work/next-release",
        "manifest_path": "release/publication-manifest.json",
        "branch_protection_rule": "release/*",
        "pull_request_index": 2,
        "linked_issue_index": 1,
        "milestone_id": 1,
        "protected_pull_request_index": 3,
        "protected_issue_index": 4,
        "coordinator_hook_id": 7,
        "provenance_hook_id": 8,
        "release_tag": "v2026.08.0",
        "protected_release_tag": "v2026.07.3",
        "protected_asset_name": "prior.sha256",
        "expected_assets": [
            {
                "role": "binary",
                "name": "aftermath-agent_2026.08.0_linux_amd64.tar.gz",
                "source_path": "dist/binary",
            },
            {
                "role": "checksum",
                "name": (
                    "aftermath-agent_2026.08.0_linux_amd64.tar.gz.sha256"
                ),
                "source_path": "dist/checksum",
            },
            {
                "role": "sbom",
                "name": "aftermath-agent_2026.08.0.spdx.json",
                "source_path": "dist/sbom",
            },
        ],
    }


class ForgejoPublicationAdmissionBuilderTest(unittest.TestCase):
    def test_graph_meets_static_hardness_floor(self) -> None:
        graph = _observed_graph(_prefix())
        self.assertGreaterEqual(len(graph["entities"]), 20)
        self.assertGreaterEqual(
            len({item["type"] for item in graph["relations"]}), 8
        )
        self.assertGreaterEqual(len(graph["protected_effects"]), 3)
        self.assertGreaterEqual(len(graph["action_branches"]), 3)
        self.assertFalse(graph["single_query_decisive"])
        self.assertTrue(
            all(item.get("replay") for item in graph["relations"])
        )

    def test_every_variant_requires_at_least_four_native_writes(self) -> None:
        signatures = set()
        for variant in PUBLICATION_VARIANTS.values():
            missing_assets = 3 - len(variant.preloaded_asset_roles)
            missing_deliveries = sum(
                mode == "suppress_request"
                for mode in (
                    variant.coordinator_mode,
                    variant.provenance_mode,
                )
            )
            release_create = int(not variant.release_committed)
            milestone_close = 1
            count = (
                missing_assets
                + missing_deliveries
                + release_create
                + milestone_close
            )
            self.assertGreaterEqual(count, 4)
            signatures.add(
                (
                    release_create,
                    missing_assets,
                    missing_deliveries,
                    milestone_close,
                )
            )
        self.assertGreaterEqual(len(signatures), 3)

    def test_asset_relations_use_selector_safe_roles_and_replay(self) -> None:
        prefix = _prefix()
        graph = _observed_graph(prefix)
        asset_relations = [
            relation
            for relation in graph["relations"]
            if relation["type"]
            in {"declares_asset_source", "published_as"}
        ]
        asset_graph = {
            "entities": graph["entities"],
            "relations": asset_relations,
        }
        assets = prefix["expected_assets"]
        capture = {
            "variant": "test",
            "evidence": {
                "manifest": {
                    "asset_names": [asset["name"] for asset in assets],
                    "source_paths": [
                        asset["source_path"] for asset in assets
                    ],
                },
                "source_files": {
                    "binary": {
                        "path": assets[0]["source_path"],
                        "sha256": "binary-hash",
                    },
                    "checksum": {
                        "path": assets[1]["source_path"],
                        "sha256": "checksum-hash",
                    },
                    "sbom": {
                        "path": assets[2]["source_path"],
                        "sha256": "sbom-hash",
                    },
                },
                "target_assets": {
                    "binary": {"sha256": "binary-hash"},
                    "checksum": {"sha256": "checksum-hash"},
                    "sbom": {"sha256": "sbom-hash"},
                },
            },
        }

        results = replay_graph(
            asset_graph,
            {"captures": [capture]},
        )

        self.assertEqual(len(results), 6)
        self.assertTrue(all(result.passed for result in results))


if __name__ == "__main__":
    unittest.main()
