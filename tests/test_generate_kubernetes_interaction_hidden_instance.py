from __future__ import annotations

import unittest

from aftermath_bench.integrations.kubernetes_interaction_instance import (
    DEFAULT_KUBERNETES_INTERACTION_INSTANCE,
    KubernetesInteractionInstanceSpec,
)
from scripts.generate_kubernetes_interaction_hidden_instance import build_instance
from scripts.verify_kubernetes_interaction_instance_novelty import (
    semantic_change_report,
)


class GenerateKubernetesInteractionHiddenInstanceTests(unittest.TestCase):
    def test_generated_instance_is_valid_and_semantically_novel(self) -> None:
        instance = KubernetesInteractionInstanceSpec.from_dict(
            build_instance("test-001")
        )
        instance.validate()
        self.assertTrue(semantic_change_report(instance)["passed"])
        self.assertNotEqual(instance.namespace, DEFAULT_KUBERNETES_INTERACTION_INSTANCE.namespace)
        self.assertTrue(instance.migration_generate_name.endswith("-"))

    def test_each_generated_instance_has_a_new_identity(self) -> None:
        first = KubernetesInteractionInstanceSpec.from_dict(build_instance("test-001"))
        second = KubernetesInteractionInstanceSpec.from_dict(build_instance("test-002"))
        self.assertNotEqual(first.scenario_id, second.scenario_id)
        self.assertNotEqual(first.namespace, second.namespace)
        self.assertNotEqual(first.sha256, second.sha256)


if __name__ == "__main__":
    unittest.main()
