from __future__ import annotations

import unittest
from pathlib import Path

from aftermath_bench.integrations.kubernetes_interaction_faults import SURFACE_ERROR
from aftermath_bench.integrations.kubernetes_interaction_scope import (
    INTERACTION_VARIANT_FACTS,
    derive_interaction_scope,
)
from aftermath_bench.native_kubernetes_interaction_family import (
    KUBERNETES_INTERACTION_FAMILY,
    KUBERNETES_INTERACTION_SYSTEM_PROMPT,
    kubernetes_interaction_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_scenario import load_native_scenario


def _scenario():
    return load_native_scenario(
        Path(
            "data/scenario_blueprints/"
            "k8s-constraint-interactions-dev-005/scenario.json"
        )
    )


class NativeKubernetesInteractionFamilyTest(unittest.TestCase):
    def test_family_is_registered_with_generic_tools(self) -> None:
        family = NATIVE_FAMILY_REGISTRY.get(
            "k8s-constraint-interaction-recovery"
        )
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
        self.assertIn("bridge active", message)
        self.assertIn("one suspended transition owner", message)


if __name__ == "__main__":
    unittest.main()
