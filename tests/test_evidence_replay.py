from __future__ import annotations

import unittest

from aftermath_bench.evidence_replay import replay_graph, select_values


class EvidenceReplayTest(unittest.TestCase):
    def test_selector_handles_nested_child_rows(self) -> None:
        evidence = {
            "invoice": {
                "items": [
                    {"purchase_receipt": "PR-1"},
                    {"purchase_receipt": "PR-2"},
                ]
            }
        }
        self.assertEqual(
            select_values(evidence, "invoice.items.*.purchase_receipt"),
            ["PR-1", "PR-2"],
        )

    def test_graph_edges_are_replayed_in_every_capture(self) -> None:
        graph = {
            "entities": [
                {"id": "receipt", "native_name": "PR-1"},
                {"id": "invoice", "native_name": "PI-1"},
            ],
            "relations": [
                {
                    "source": "receipt",
                    "target": "invoice",
                    "type": "billed_by",
                    "replay": [
                        {
                            "selector": "invoice.items.*.purchase_receipt",
                            "operator": "any_equals",
                            "expected_entity": "receipt",
                        }
                    ],
                }
            ],
        }
        captures = {
            "captures": [
                {
                    "variant": "a",
                    "evidence": {
                        "invoice": {
                            "items": [{"purchase_receipt": "PR-1"}]
                        }
                    },
                },
                {
                    "variant": "b",
                    "evidence": {
                        "invoice": {
                            "items": [{"purchase_receipt": "PR-1"}]
                        }
                    },
                },
            ]
        }
        result = replay_graph(graph, captures)
        self.assertTrue(result[0].passed, result[0].failures)
        captures["captures"][1]["evidence"]["invoice"]["items"][0][
            "purchase_receipt"
        ] = "PR-WRONG"
        result = replay_graph(graph, captures)
        self.assertFalse(result[0].passed)
        self.assertIn("b clause 0 failed", result[0].failures)


if __name__ == "__main__":
    unittest.main()
