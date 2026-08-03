from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.native_baseline_summary import summarize_baselines


class NativeBaselineSummaryTest(unittest.TestCase):
    def _write(
        self,
        root: Path,
        name: str,
        variant: str,
        passed: bool,
        *,
        integrity_key: bool = False,
    ) -> None:
        evaluation_key = (
            "recovery_integrity_pass" if integrity_key else "passed"
        )
        (root / f"{name}-{variant}.json").write_text(
            json.dumps(
                {
                    "baseline": name,
                    "variant": variant,
                    "evaluation": {evaluation_key: passed},
                }
            ),
            encoding="utf-8",
        )

    def test_rejects_a_compact_policy_that_solves_the_matched_group(self) -> None:
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

    def test_accepts_complete_low_rate_policies(self) -> None:
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

    def test_reports_missing_variant_coverage(self) -> None:
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

    def test_accepts_recovery_integrity_pass_without_silently_scoring_false(
        self,
    ) -> None:
        scenario = {
            "scenario_id": "scenario-1",
            "matched_variants": [{"id": "a"}, {"id": "b"}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self._write(
                directory, "policy", "a", True, integrity_key=True
            )
            self._write(
                directory, "policy", "b", False, integrity_key=True
            )
            report = summarize_baselines(
                run_directory=directory,
                scenario=scenario,
            )

        self.assertEqual(report["heuristics"][0]["pass_rate"], 0.5)
        self.assertFalse(report["heuristics"][0]["matched_group_success"])

    def test_prefers_integrity_result_when_legacy_pass_is_also_present(
        self,
    ) -> None:
        scenario = {
            "scenario_id": "scenario-1",
            "matched_variants": [{"id": "a"}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "policy-a.json").write_text(
                json.dumps(
                    {
                        "variant": "a",
                        "baseline": "policy",
                        "evaluation": {
                            "passed": True,
                            "recovery_integrity_pass": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            report = summarize_baselines(
                run_directory=directory,
                scenario=scenario,
            )

        self.assertEqual(report["heuristics"][0]["pass_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
