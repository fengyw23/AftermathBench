from __future__ import annotations

import importlib.util
import unittest

from aftermath_bench.native_admission import _dependency_depth
from aftermath_bench.schema import repository_root


def _builder_module():
    path = (
        repository_root()
        / "scripts"
        / "build_kubernetes_settlement_v2_admission.py"
    )
    spec = importlib.util.spec_from_file_location(
        "build_kubernetes_settlement_v2_admission", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load settlement v2 admission builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KubernetesSettlementV2AdmissionBuilderTest(unittest.TestCase):
    def test_graph_meets_static_scale_without_author_claims(self) -> None:
        graph = _builder_module()._observed_graph()
        entities = {item["id"] for item in graph["entities"]}
        relation_types = {item["type"] for item in graph["relations"]}
        self.assertGreaterEqual(len(entities), 20)
        self.assertGreaterEqual(len(relation_types), 8)
        self.assertGreaterEqual(
            _dependency_depth(entities, graph["relations"]), 5
        )
        self.assertTrue(
            all(item.get("replay") for item in graph["relations"])
        )

    def test_domain_evidence_and_action_branches_are_explicit(self) -> None:
        graph = _builder_module()._observed_graph()
        self.assertEqual(len(graph["evidence_tool_groups"]), 4)
        self.assertGreaterEqual(len(graph["action_branches"]), 3)
        self.assertFalse(graph["single_query_decisive"])


if __name__ == "__main__":
    unittest.main()
