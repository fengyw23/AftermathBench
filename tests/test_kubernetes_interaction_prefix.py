from __future__ import annotations

import json
import unittest

from aftermath_bench.integrations.kubernetes_interaction_prefix import (
    API_V1,
    API_V2,
    BATCH_STATE,
    COMPATIBILITY_BRIDGE,
    CONTRACT_CONFIGMAPS,
    CURRENT_CREDENTIAL,
    NAMESPACE,
    WORKER_V1,
    WORKER_V2,
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
            API_V1,
            API_V2,
            WORKER_V1,
            WORKER_V2,
        ):
            self.assertIn(("Deployment", name), names)
        self.assertIn(("Secret", CURRENT_CREDENTIAL), names)
        self.assertIn(("ConfigMap", COMPATIBILITY_BRIDGE), names)
        self.assertIn(("ConfigMap", BATCH_STATE), names)
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
