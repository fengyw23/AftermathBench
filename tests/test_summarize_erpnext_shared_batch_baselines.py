from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.summarize_erpnext_shared_batch_baselines import summarize
from aftermath_bench.integrations.erpnext_shared_batch_baselines import (
    SHARED_BATCH_BASELINE_NAMES,
)


SCENARIO = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "scenario_blueprints"
    / "erpnext-shared-batch-recovery-dev-001"
    / "scenario.json"
)


class SharedBatchBaselineSummaryTest(unittest.TestCase):
    def test_rejects_a_universal_fixed_strategy(self) -> None:
        variants = tuple(
            row["id"]
            for row in json.loads(SCENARIO.read_text(encoding="utf-8"))[
                "matched_variants"
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for baseline in SHARED_BATCH_BASELINE_NAMES:
                for variant in variants:
                    passed = baseline == "blind_retry"
                    (directory / f"{baseline}-{variant}.json").write_text(
                        json.dumps({"evaluation": {"passed": passed}}),
                        encoding="utf-8",
                    )
            result = summarize(directory, SCENARIO)
        self.assertFalse(result["passed"])
        self.assertEqual(result["universal_baselines"], ["blind_retry"])
        self.assertEqual(result["maximum_pass_rate"], 1)

    def test_accepts_complete_non_universal_matrix(self) -> None:
        variants = tuple(
            row["id"]
            for row in json.loads(SCENARIO.read_text(encoding="utf-8"))[
                "matched_variants"
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for baseline in SHARED_BATCH_BASELINE_NAMES:
                for index, variant in enumerate(variants):
                    passed = baseline == "blind_retry" and index == 0
                    (directory / f"{baseline}-{variant}.json").write_text(
                        json.dumps({"evaluation": {"passed": passed}}),
                        encoding="utf-8",
                    )
            result = summarize(directory, SCENARIO)
        self.assertTrue(result["passed"])
        self.assertEqual(result["maximum_pass_rate"], 0.25)
        self.assertEqual(result["missing_reports"], [])

    def test_rejects_a_strategy_that_solves_half_the_boundaries(self) -> None:
        variants = tuple(
            row["id"]
            for row in json.loads(SCENARIO.read_text(encoding="utf-8"))[
                "matched_variants"
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for baseline in SHARED_BATCH_BASELINE_NAMES:
                for index, variant in enumerate(variants):
                    passed = baseline == "blind_retry" and index < 2
                    (directory / f"{baseline}-{variant}.json").write_text(
                        json.dumps({"evaluation": {"passed": passed}}),
                        encoding="utf-8",
                    )
            result = summarize(directory, SCENARIO)
        self.assertFalse(result["passed"])
        self.assertEqual(result["maximum_pass_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
