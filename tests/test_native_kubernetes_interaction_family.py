from __future__ import annotations

import unittest
from pathlib import Path

from aftermath_bench.integrations.kubernetes_interaction_faults import SURFACE_ERROR
from aftermath_bench.integrations.kubernetes_interaction_prefix import (
    API_V2,
    NEXT_CREDENTIAL,
    RECOVERY_AUDIT_KEY,
    REGISTRY_COMPENSATION_KEY,
    REGISTRY_PREPARE_KEY,
    REGISTRY_RELEASE_KEY,
    REGISTRY_STABLE_KEY,
    WORKER_V2,
)
from aftermath_bench.integrations.kubernetes_interaction_recovery import (
    _expected_terminal,
)
from aftermath_bench.integrations.kubernetes_interaction_scope import (
    INTERACTION_VARIANT_FACTS,
    derive_interaction_scope,
)
from aftermath_bench.native_kubernetes_interaction_family import (
    KUBERNETES_INTERACTION_FAMILY,
    KUBERNETES_INTERACTION_SYSTEM_PROMPT,
    _control_target,
    kubernetes_interaction_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_scenario import load_native_scenario


def _scenario():
    return load_native_scenario(
        Path(
            "data/scenario_blueprints/k8s-constraint-interactions-dev-005/scenario.json"
        )
    )


class NativeKubernetesInteractionFamilyTest(unittest.TestCase):
    def test_family_is_registered_with_generic_tools(self) -> None:
        family = NATIVE_FAMILY_REGISTRY.get("k8s-constraint-interaction-recovery")
        self.assertIs(family, KUBERNETES_INTERACTION_FAMILY)
        names = {tool.name for tool in family.tool_definitions}
        self.assertIn("get_object", names)
        self.assertIn("patch_object", names)
        self.assertIn("post_external_event", names)
        self.assertFalse(any(name.startswith("repair_") for name in names))

    def test_ordinary_message_hides_variant_and_scope(self) -> None:
        message = kubernetes_interaction_initial_message(
            scenario=_scenario(),
            prefix={"trace": []},
            failure_report={
                "variant": "state_05",
                "visible_failure": {"ok": False, "error": SURFACE_ERROR},
            },
        )
        self.assertNotIn("state_05", message)
        for facts in INTERACTION_VARIANT_FACTS.values():
            label = derive_interaction_scope(facts)
            self.assertNotIn(label, message)
            self.assertNotIn(label, KUBERNETES_INTERACTION_SYSTEM_PROMPT)

    def test_execution_control_supplies_target_without_variant_label(self) -> None:
        message = kubernetes_interaction_initial_message(
            scenario=_scenario(),
            prefix={"trace": []},
            failure_report={
                "variant": "state_05",
                "visible_failure": {"ok": False, "error": SURFACE_ERROR},
            },
            execution_control=True,
        )
        self.assertNotIn("state_05", message)
        self.assertIn('"bridge_lease": "active"', message)
        self.assertIn("one suspended transition Job", message)
        self.assertIn('"compensation_required": false', message)

    def test_aborted_control_unambiguously_removes_only_candidate_artifacts(
        self,
    ) -> None:
        target = _control_target("state_02")
        self.assertEqual(
            target["terminal_state"]["target_candidate_artifacts"],
            "absent",
        )
        self.assertEqual(
            target["candidate_artifact_disposition"],
            {
                API_V2: "delete",
                WORKER_V2: "delete",
                NEXT_CREDENTIAL: "delete",
            },
        )
        preservation = target["preservation"]
        self.assertIn("governed only by candidate_artifact_disposition", preservation)
        self.assertIn("delete exactly those three when it says delete", preservation)
        self.assertNotIn("Preserve every pre-existing", preservation)

    def test_committed_control_preserves_candidate_artifacts(self) -> None:
        target = _control_target("state_10")
        self.assertEqual(
            target["terminal_state"]["target_candidate_artifacts"],
            "present",
        )
        self.assertEqual(
            set(target["candidate_artifact_disposition"].values()),
            {"preserve"},
        )

    def test_control_target_matches_evaluator_terminal_for_every_variant(
        self,
    ) -> None:
        for variant, boundary in INTERACTION_VARIANT_FACTS.items():
            with self.subTest(variant=variant):
                expected = _expected_terminal(boundary)
                target = _control_target(variant)
                terminal = target["terminal_state"]
                records = target["records"]
                external = target["external_registry"]
                self.assertEqual(terminal["catalog_schema_epoch"], expected["epoch"])
                self.assertEqual(terminal["release_ledger_status"], expected["status"])
                self.assertEqual(terminal["api_version"], expected["api_version"])
                self.assertEqual(terminal["worker_version"], expected["worker_version"])
                self.assertEqual(
                    terminal["shared_credential_generation"],
                    expected["credential_generation"],
                )
                self.assertEqual(
                    records["recovery_audit"][
                        "orders-platform-v2.preparation_resolution"
                    ],
                    expected["preparation_resolution"],
                )
                self.assertEqual(
                    set(external["allowed_final_keys_exactly_once"]),
                    set(expected["allowed_external_keys"]),
                )
                self.assertEqual(
                    external["compensation_required"],
                    expected["compensation_required"],
                )

    def test_external_control_envelope_flips_only_when_justified(self) -> None:
        no_prepare = _control_target("state_01")["external_registry"]
        prepared = _control_target("state_02")["external_registry"]
        active = _control_target("state_10")["external_registry"]

        self.assertEqual(
            set(no_prepare["allowed_final_keys_exactly_once"]),
            {REGISTRY_STABLE_KEY, RECOVERY_AUDIT_KEY},
        )
        self.assertFalse(no_prepare["compensation_required"])
        self.assertNotIn(
            REGISTRY_COMPENSATION_KEY,
            no_prepare["allowed_final_keys_exactly_once"],
        )

        self.assertEqual(
            set(prepared["allowed_final_keys_exactly_once"]),
            {
                REGISTRY_STABLE_KEY,
                REGISTRY_PREPARE_KEY,
                REGISTRY_COMPENSATION_KEY,
                RECOVERY_AUDIT_KEY,
            },
        )
        self.assertTrue(prepared["compensation_required"])

        self.assertEqual(
            set(active["allowed_final_keys_exactly_once"]),
            {
                REGISTRY_STABLE_KEY,
                REGISTRY_RELEASE_KEY,
                RECOVERY_AUDIT_KEY,
            },
        )
        self.assertFalse(active["compensation_required"])


if __name__ == "__main__":
    unittest.main()
