from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock

from aftermath_bench.integrations.kubernetes_constraint_faults import (
    KUBERNETES_CONSTRAINT_VARIANTS,
    SURFACE_ERROR,
    KubernetesConstraintFaultBoundary,
)
from aftermath_bench.integrations.kubernetes_constraint_prefix import (
    constraint_prefix_manifests,
)
from aftermath_bench.integrations.kubernetes_constraint_recovery import (
    derive_constraint_scope,
)
from aftermath_bench.kubernetes_constraint_prompt_audit import (
    build_constraint_prompt_audit,
)
from aftermath_bench.native_admission import (
    _constraint_prompt_admission,
    _dependency_depth,
)
from aftermath_bench.native_kubernetes_constraint_family import (
    KUBERNETES_CONSTRAINT_SYSTEM_PROMPT,
    kubernetes_constraint_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_scenario import load_native_scenario
from scripts.build_kubernetes_constraint_admission import _observed_graph


def _scenario():
    return load_native_scenario(
        Path("data/scenario_blueprints/k8s-constraint-scope-dev-004/scenario.json")
    )


def _variant_facts() -> dict[str, dict]:
    return {
        "failed_migration_without_preparation": {
            "epoch": "1",
            "job": "failed",
            "service": "v1",
            "preparation": False,
            "publication": False,
        },
        "failed_migration_with_preparation": {
            "epoch": "1",
            "job": "failed",
            "service": "v1",
            "preparation": True,
            "publication": False,
        },
        "committed_cutover_without_publication": {
            "epoch": "2",
            "job": "complete",
            "service": "v2",
            "preparation": False,
            "publication": False,
        },
        "committed_cutover_with_publication": {
            "epoch": "2",
            "job": "complete",
            "service": "v2",
            "preparation": False,
            "publication": True,
        },
    }


class KubernetesConstraintPromptTest(unittest.TestCase):
    def test_ordinary_prompt_contains_constraints_not_branch_answers(self) -> None:
        scenario = _scenario()
        message = kubernetes_constraint_initial_message(
            scenario=scenario,
            prefix={"trace": []},
            failure_report={
                "variant": "failed_migration_with_preparation",
                "visible_failure": {"ok": False, "error": SURFACE_ERROR},
            },
        )
        hidden_labels = (
            "rollback_to_stable",
            "compensate_external_effect",
            "forward_complete",
            "repair_downstream_only",
            "discard_uncommitted_candidate",
            "compensate_then_discard_candidate",
            "publish_committed_cutover",
            "close_already_published_cutover",
        )
        self.assertNotIn("failed_migration_with_preparation", message)
        for label in hidden_labels:
            self.assertNotIn(label, message)
            self.assertNotIn(label, KUBERNETES_CONSTRAINT_SYSTEM_PROMPT)

    def test_prompt_audit_is_derived_from_actual_visible_surfaces(self) -> None:
        scenario = _scenario()
        audit = build_constraint_prompt_audit(
            scenario,
            variant_facts=_variant_facts(),
            prefix_trace=[],
            visible_failure={"ok": False, "error": SURFACE_ERROR},
        )
        checks, observed = _constraint_prompt_admission(
            audit,
            minimum_counterfactual_flips=2,
            expected_variants=set(scenario.variants),
        )
        self.assertTrue(all(checks.values()), checks)
        self.assertEqual(observed["ordinary_visible_surface_count"], 13)
        self.assertEqual(observed["single_fact_direction_flip_count"], 2)
        self.assertEqual(
            [pair["changed_facts"] for pair in audit["counterfactual_pairs"]],
            [["preparation"], ["publication"]],
        )

    def test_native_contracts_do_not_store_scope_labels(self) -> None:
        text = str(constraint_prefix_manifests())
        for label in _scenario().raw["required_semantic_recovery_directions"]:
            self.assertNotIn(label, text)

    def test_external_payload_and_record_update_rules_are_visible(self) -> None:
        manifests = {
            item["metadata"]["name"]: item.get("data", {})
            for item in constraint_prefix_manifests()
            if item.get("kind") == "ConfigMap"
        }
        registry = manifests["registry-contract"]
        audit = manifests["audit-contract"]
        self.assertIn("compensates", registry["compensationPayloadFields"])
        self.assertIn("migration_job_uid", registry["releasePayloadFields"])
        self.assertIn("not-created iff", registry["preparationResolutionRule"])
        self.assertIn("preserve every", audit["recordUpdateRule"])

    def test_family_is_routable(self) -> None:
        family = NATIVE_FAMILY_REGISTRY.get("k8s-constraint-scope-recovery")
        self.assertEqual(family.domain, "kubernetes")

    def test_replay_graph_requires_composed_constraints(self) -> None:
        graph = _observed_graph()
        entity_ids = {item["id"] for item in graph["entities"]}
        self.assertGreaterEqual(len(entity_ids), 20)
        self.assertGreaterEqual(_dependency_depth(entity_ids, graph["relations"]), 5)
        self.assertGreaterEqual(
            len({item["type"] for item in graph["relations"]}),
            8,
        )
        self.assertFalse(
            any(
                item["type"] == "selects_recovery_direction"
                for item in graph["relations"]
            )
        )

    def test_runtime_workflow_replays_references_and_baselines(self) -> None:
        workflow = Path(
            ".github/workflows/kubernetes-constraint-runtime.yml"
        ).read_text(encoding="utf-8")
        for variant in _scenario().variants:
            self.assertIn(variant, workflow)
        for script in (
            "run_kubernetes_constraint_boundary.py",
            "run_kubernetes_constraint_control.py",
            "run_kubernetes_constraint_baseline.py",
            "build_kubernetes_constraint_admission.py",
        ):
            self.assertIn(script, workflow)

    def test_model_workflow_uses_secret_and_all_matched_states(self) -> None:
        workflow = Path(".github/workflows/kubernetes-constraint-model.yml").read_text(
            encoding="utf-8"
        )
        for variant in _scenario().variants:
            self.assertIn(variant, workflow)
        self.assertIn("secrets.BAILIAN_API_KEY", workflow)
        self.assertNotIn("sk-", workflow)
        self.assertIn("for attempt in 1 2", workflow)
        self.assertIn("--execution-control", workflow)
        self.assertIn("--model-timeout-seconds 300", workflow)
        self.assertIn('rm -f "$run_root/credentials.json"', workflow)


class KubernetesConstraintBoundaryTest(unittest.TestCase):
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

    def test_all_variants_expose_the_same_error(self) -> None:
        for variant in KUBERNETES_CONSTRAINT_VARIANTS:
            with self.subTest(variant=variant):
                boundary = KubernetesConstraintFaultBoundary(
                    self._api(),
                    json_request=Mock(return_value={"attempt_count": 1}),
                )
                with self.assertRaisesRegex(ConnectionError, SURFACE_ERROR):
                    boundary.trigger(variant)

    def test_four_scopes_are_derived_from_native_facts(self) -> None:
        expected = {
            "failed_migration_without_preparation": "discard_uncommitted_candidate",
            "failed_migration_with_preparation": ("compensate_then_discard_candidate"),
            "committed_cutover_without_publication": "publish_committed_cutover",
            "committed_cutover_with_publication": ("close_already_published_cutover"),
        }
        for variant, facts in _variant_facts().items():
            boundary = {
                "schema_epoch": facts["epoch"],
                "external_keys": [
                    *(["prepare:orders-v2"] if facts["preparation"] else []),
                    *(["release:orders-v2"] if facts["publication"] else []),
                ],
            }
            self.assertEqual(derive_constraint_scope(boundary), expected[variant])


if __name__ == "__main__":
    unittest.main()
