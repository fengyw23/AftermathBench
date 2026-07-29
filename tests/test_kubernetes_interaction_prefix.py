from __future__ import annotations

import json
import unittest

from aftermath_bench.integrations.kubernetes_interaction_prefix import (
    CONTRACT_CONFIGMAPS,
    NAMESPACE,
    interaction_prefix_manifests,
)
from aftermath_bench.integrations.kubernetes_interaction_scope import (
    INTERACTION_VARIANT_FACTS,
    derive_interaction_scope,
)


class KubernetesInteractionPrefixTest(unittest.TestCase):
    def test_prefix_has_native_two_consumer_and_shared_dependency_objects(self) -> None:
        manifests = interaction_prefix_manifests()
        names = {
            (item["kind"], item["metadata"].get("name")) for item in manifests
        }
        self.assertGreaterEqual(len(manifests), 20)
        for name in (
            "orders-api-v1",
            "orders-api-v2",
            "orders-worker-v1",
            "orders-worker-v2",
        ):
            self.assertIn(("Deployment", name), names)
        self.assertIn(("Secret", "orders-db-current"), names)
        self.assertIn(("ConfigMap", "schema-compatibility-bridge"), names)
        self.assertIn(("ConfigMap", "worker-batch-state"), names)
        self.assertTrue(
            set(CONTRACT_CONFIGMAPS)
            <= {name for kind, name in names if kind == "ConfigMap"}
        )

    def test_every_namespaced_manifest_uses_interaction_namespace(self) -> None:
        for manifest in interaction_prefix_manifests():
            if manifest["kind"] == "Namespace":
                continue
            self.assertEqual(manifest["metadata"].get("namespace"), NAMESPACE)

    def test_visible_contracts_do_not_contain_evaluator_scope_labels(self) -> None:
        rendered = json.dumps(interaction_prefix_manifests(), sort_keys=True)
        for facts in INTERACTION_VARIANT_FACTS.values():
            self.assertNotIn(derive_interaction_scope(facts), rendered)


if __name__ == "__main__":
    unittest.main()
