from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.native_baseline_summary import summarize_baselines


class NativeBaselineSummaryTest(unittest.TestCase):
    def test_accepts_recovery_integrity_pass_without_silently_scoring_false(self) -> None:
        scenario = {
            "scenario_id": "scenario-1",
            "matched_variants": [{"id": "a"}, {"id": "b"}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for variant, passed in (("a", True), ("b", False)):
                (directory / f"policy-{variant}.json").write_text(
                    json.dumps(
                        {
                            "variant": variant,
                            "baseline": "policy",
                            "evaluation": {"recovery_integrity_pass": passed},
                        }
                    ),
                    encoding="utf-8",
                )
            report = summarize_baselines(
                run_directory=directory,
                scenario=scenario,
            )

        self.assertEqual(report["heuristics"][0]["pass_rate"], 0.5)
        self.assertFalse(report["heuristics"][0]["matched_group_success"])

    def test_prefers_integrity_result_when_legacy_pass_is_also_present(self) -> None:
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
