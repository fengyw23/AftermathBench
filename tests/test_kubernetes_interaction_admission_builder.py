from __future__ import annotations

import importlib.util
import unittest

from aftermath_bench.native_admission import (
    _dependency_depth,
    _shared_dependency_count,
)
from aftermath_bench.schema import repository_root


def _builder_module():
    path = (
        repository_root()
        / "scripts"
        / "build_kubernetes_interaction_admission.py"
    )
    spec = importlib.util.spec_from_file_location(
        "build_kubernetes_interaction_admission", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load interaction admission builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KubernetesInteractionAdmissionBuilderTest(unittest.TestCase):
    def test_graph_meets_static_hardness_floor(self) -> None:
        graph = _builder_module()._observed_graph()
        entities = {str(item["id"]) for item in graph["entities"]}
        relation_types = {str(item["type"]) for item in graph["relations"]}
        self.assertGreaterEqual(len(entities), 20)
        self.assertGreaterEqual(len(relation_types), 8)
        self.assertGreaterEqual(
            _dependency_depth(entities, graph["relations"]), 5
        )
        self.assertGreaterEqual(
            _shared_dependency_count(
                graph["protected_effects"], graph["relations"]
            ),
            2,
        )
        self.assertTrue(all(item.get("replay") for item in graph["relations"]))

    def test_evidence_and_action_families_are_explicit(self) -> None:
        graph = _builder_module()._observed_graph()
        self.assertEqual(len(graph["evidence_tool_groups"]), 6)
        self.assertGreaterEqual(len(graph["action_branches"]), 3)
        self.assertGreaterEqual(
            graph["minimum_semantic_recovery_directions"], 8
        )
        self.assertFalse(graph["single_query_decisive"])


if __name__ == "__main__":
    unittest.main()
