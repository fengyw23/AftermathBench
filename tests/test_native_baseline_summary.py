from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.summarize_native_baselines import summarize_baselines


class NativeBaselineSummaryTest(unittest.TestCase):
    def _write(self, root, name, variant, passed):
        (root / f"{name}-{variant}.json").write_text(
            json.dumps(
                {
                    "baseline": name,
                    "variant": variant,
                    "evaluation": {"passed": passed},
                }
            ),
            encoding="utf-8",
        )

    def test_rejects_a_compact_policy_that_solves_the_matched_group(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for variant in ("a", "b", "c", "d"):
                self._write(root, "no_op", variant, False)
                self._write(root, "compact_tree", variant, True)
            summary = summarize_baselines(
                run_directory=root,
                scenario={
                    "scenario_id": "example",
                    "matched_variants": [
                        {"id": item} for item in ("a", "b", "c", "d")
                    ],
                },
            )
        self.assertFalse(summary["hard_fixed_policy_gate_passed"])
        self.assertEqual(summary["maximum_heuristic_pass_rate"], 1.0)
        self.assertEqual(summary["matched_group_solvers"], ["compact_tree"])

    def test_accepts_complete_low_rate_policies(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            variants = ("a", "b", "c", "d")
            for variant in variants:
                self._write(root, "no_op", variant, False)
                self._write(root, "blind_retry", variant, variant == "a")
            summary = summarize_baselines(
                run_directory=root,
                scenario={
                    "scenario_id": "example",
                    "matched_variants": [
                        {"id": item} for item in variants
                    ],
                },
            )
        self.assertTrue(summary["hard_fixed_policy_gate_passed"])
        self.assertEqual(summary["maximum_heuristic_pass_rate"], 0.25)

    def test_reports_missing_variant_coverage(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._write(root, "no_op", "a", False)
            summary = summarize_baselines(
                run_directory=root,
                scenario={
                    "scenario_id": "example",
                    "matched_variants": [{"id": "a"}, {"id": "b"}],
                },
            )
        self.assertEqual(summary["coverage_errors"][0]["missing"], ["b"])
        self.assertFalse(summary["hard_fixed_policy_gate_passed"])


if __name__ == "__main__":
    unittest.main()
