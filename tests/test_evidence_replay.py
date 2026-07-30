from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.evidence_replay import replay_graph, select_values
from aftermath_bench.native_admission import validate_native_scenario
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root


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

    def test_native_admission_rejects_incomplete_capture_coverage(self) -> None:
        source = (
            repository_root()
            / "data"
            / "scenarios"
            / "erpnext-sales-return-dev-001"
        )
        with TemporaryDirectory() as directory:
            target = Path(directory) / "scenario"
            target.mkdir()
            (target / "artifacts").mkdir()
            scenario = deepcopy(
                load_native_scenario(source / "scenario.json").raw
            )
            for relative in scenario["admission_artifacts"].values():
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(
                    (source / relative).read_bytes()
                )
            replay_path = target / scenario["admission_artifacts"][
                "replay_evidence"
            ]
            replay = __import__("json").loads(
                replay_path.read_text(encoding="utf-8")
            )
            replay["captures"] = replay["captures"][:1]
            replay_path.write_text(
                __import__("json").dumps(replay, indent=2) + "\n",
                encoding="utf-8",
            )
            scenario_path = target / "scenario.json"
            scenario_path.write_text(
                __import__("json").dumps(scenario, indent=2) + "\n",
                encoding="utf-8",
            )
            report = validate_native_scenario(
                load_native_scenario(scenario_path)
            )
            self.assertFalse(
                report.checks[
                    "replay_captures_cover_variants_exactly_once"
                ]
            )


if __name__ == "__main__":
    unittest.main()
