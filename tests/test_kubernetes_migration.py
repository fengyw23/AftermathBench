from __future__ import annotations

import json
import unittest
from unittest.mock import Mock

from aftermath_bench.integrations.kubernetes_migration_faults import (
    KUBERNETES_MIGRATION_VARIANTS,
    SURFACE_ERROR,
    KubernetesMigrationFaultBoundary,
)
from aftermath_bench.integrations.kubernetes_migration_prefix import (
    prefix_manifests,
)
from aftermath_bench.integrations.kubernetes_migration_recovery import (
    derive_recovery_direction,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_admission import (
    _dependency_depth,
    _shared_dependency_count,
)
from aftermath_bench.schema import repository_root
from scripts.build_kubernetes_migration_admission import _observed_graph


class KubernetesMigrationBlueprintTest(unittest.TestCase):
    def test_policy_exposes_every_scored_recovery_branch(self) -> None:
        policy = next(
            item
            for item in prefix_manifests()
            if item["kind"] == "ConfigMap"
            and item["metadata"].get("name") == "recovery-policy"
        )["data"]
        self.assertEqual(policy["epoch1Action"], "rollback_to_stable")
        self.assertEqual(
            policy["epoch1WithEscapedPreparationAction"],
            "compensate_external_effect",
        )
        self.assertEqual(policy["epoch2BeforeCutoverAction"], "forward_complete")
        self.assertEqual(
            policy["epoch2AfterPublishedCutoverAction"],
            "repair_downstream_only",
        )
        self.assertIn("deployment/orders-v2", policy["abortCandidateResources"])
        self.assertEqual(policy["downMigrationAllowed"], "false")

    def test_scenario_has_four_distinct_directions(self) -> None:
        scenario = json.loads(
            (
                repository_root()
                / "data"
                / "scenario_blueprints"
                / "k8s-schema-rollout-dev-003"
                / "scenario.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(len(scenario["matched_variants"]), 4)
        self.assertEqual(len(set(scenario["required_semantic_recovery_directions"])), 4)

    def test_family_is_registered(self) -> None:
        family = NATIVE_FAMILY_REGISTRY.get("k8s-schema-rollout-recovery")
        self.assertEqual(family.domain, "kubernetes")
        self.assertIn(
            "wait_for_deployment",
            {tool.name for tool in family.tool_definitions},
        )
        self.assertNotIn(
            "remove_node_taint",
            {tool.name for tool in family.tool_definitions},
        )
        external = next(
            tool
            for tool in family.tool_definitions
            if tool.name == "post_external_event"
        )
        self.assertIn("release registry", external.description)

    def test_workflows_cover_boundaries_controls_and_secret_model_access(self) -> None:
        root = repository_root() / ".github" / "workflows"
        runtime = (root / "kubernetes-migration-runtime.yml").read_text(
            encoding="utf-8"
        )
        model = (root / "kubernetes-migration-model.yml").read_text(encoding="utf-8")
        for variant in KUBERNETES_MIGRATION_VARIANTS:
            self.assertIn(variant, runtime)
            self.assertIn(variant, model)
        for script in (
            "run_kubernetes_migration_boundary.py",
            "run_kubernetes_migration_control.py",
            "run_kubernetes_migration_baseline.py",
            "build_kubernetes_migration_admission.py",
        ):
            self.assertIn(script, runtime)
        self.assertIn("secrets.BAILIAN_API_KEY", model)
        self.assertNotIn("sk-", model)

    def test_replay_graph_meets_structural_hardness_floor(self) -> None:
        graph = _observed_graph()
        entity_ids = {entity["id"] for entity in graph["entities"]}
        self.assertGreaterEqual(len(entity_ids), 20)
        self.assertGreaterEqual(_dependency_depth(entity_ids, graph["relations"]), 5)
        self.assertGreaterEqual(
            len({relation["type"] for relation in graph["relations"]}), 8
        )
        self.assertGreaterEqual(
            _shared_dependency_count(graph["protected_effects"], graph["relations"]),
            2,
        )
        self.assertEqual(graph["minimum_semantic_recovery_directions"], 4)


class KubernetesMigrationDirectionTest(unittest.TestCase):
    def test_direction_is_derived_only_from_boundary_facts(self) -> None:
        cases = (
            (
                {
                    "schema_epoch": "1",
                    "service_version": "v1",
                    "external_keys": ["release:orders-v1"],
                },
                "rollback_to_stable",
            ),
            (
                {
                    "schema_epoch": "1",
                    "service_version": "v1",
                    "external_keys": [
                        "release:orders-v1",
                        "prepare:orders-v2",
                    ],
                },
                "compensate_external_effect",
            ),
            (
                {
                    "schema_epoch": "2",
                    "service_version": "v1",
                    "external_keys": ["release:orders-v1"],
                },
                "forward_complete",
            ),
            (
                {
                    "schema_epoch": "2",
                    "service_version": "v2",
                    "external_keys": [
                        "release:orders-v1",
                        "release:orders-v2",
                    ],
                },
                "repair_downstream_only",
            ),
        )
        for facts, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(derive_recovery_direction(facts), expected)


class KubernetesMigrationFaultTest(unittest.TestCase):
    def _api(self) -> Mock:
        api = Mock()
        api.create.return_value = {
            "metadata": {"name": "orders-schema-v2-abc", "uid": "job-uid"}
        }
        api.get.return_value = {
            "metadata": {"name": "orders-schema-v2-abc", "uid": "job-uid"},
            "status": {"succeeded": 1, "conditions": []},
        }
        return api

    def test_all_variants_share_one_surface_error(self) -> None:
        for variant in KUBERNETES_MIGRATION_VARIANTS:
            with self.subTest(variant=variant):
                boundary = KubernetesMigrationFaultBoundary(
                    self._api(), json_request=Mock(return_value={"attempt_count": 1})
                )
                with self.assertRaisesRegex(ConnectionError, SURFACE_ERROR):
                    boundary.trigger(variant)


if __name__ == "__main__":
    unittest.main()
