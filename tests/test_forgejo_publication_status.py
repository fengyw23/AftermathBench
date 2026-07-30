from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_forgejo_publication_status import (
    build_publication_status,
)


class ForgejoPublicationStatusTests(unittest.TestCase):
    @staticmethod
    def _write_summary(
        path: Path,
        *,
        passed_runs: int,
        expected_cases: int = 8,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "completed_runs": expected_cases,
                    "run_errors": [],
                    "task_pass_rate": passed_runs / expected_cases,
                    "reports": [
                        {
                            "variant": f"state-{index}",
                            "passed": index < passed_runs,
                        }
                        for index in range(expected_cases)
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_low_control_score_is_preserved_as_diagnostic_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "summary.json"
            sentinel = root / "provider-scan.ok"
            scenario = root / "scenario.json"
            output = root / "publication-status.json"
            self._write_summary(summary, passed_runs=3)
            sentinel.touch()
            scenario.write_text("{}", encoding="utf-8")

            status = build_publication_status(
                summary_path=summary,
                formal_declarations_path=root / "missing.json",
                provider_scan_sentinel_path=sentinel,
                scenario_path=scenario,
                output_path=output,
                expected_cases=8,
                minimum_pass_rate=0.8,
            )

            self.assertFalse(status["control_gate_pass"])
            self.assertFalse(status["formal_complete"])
            self.assertFalse(status["release_promotion_eligible"])
            self.assertEqual(status["control"]["passed_runs"], 3)
            self.assertEqual(status["control"]["task_pass_rate"], 0.375)
            self.assertTrue(output.is_file())

    def test_formal_release_requires_completion_and_control_gate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "summary.json"
            declarations = root / "declarations.json"
            sentinel = root / "provider-scan.ok"
            scenario = root / "scenario.json"
            self._write_summary(summary, passed_runs=7)
            declarations.write_text('{"complete":true}', encoding="utf-8")
            sentinel.touch()
            scenario.write_text("{}", encoding="utf-8")

            status = build_publication_status(
                summary_path=summary,
                formal_declarations_path=declarations,
                provider_scan_sentinel_path=sentinel,
                scenario_path=scenario,
                output_path=root / "status.json",
                expected_cases=8,
                minimum_pass_rate=0.8,
            )

            self.assertTrue(status["control_gate_pass"])
            self.assertTrue(status["formal_complete"])
            self.assertTrue(status["release_promotion_eligible"])

    def test_missing_safety_sentinel_or_scenario_is_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "summary.json"
            scenario = root / "scenario.json"
            self._write_summary(summary, passed_runs=8)
            scenario.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sentinel"):
                build_publication_status(
                    summary_path=summary,
                    formal_declarations_path=root / "missing.json",
                    provider_scan_sentinel_path=root / "missing.ok",
                    scenario_path=scenario,
                    output_path=root / "status.json",
                    expected_cases=8,
                    minimum_pass_rate=0.8,
                )

            sentinel = root / "provider-scan.ok"
            sentinel.touch()
            scenario.unlink()
            with self.assertRaisesRegex(ValueError, "scenario"):
                build_publication_status(
                    summary_path=summary,
                    formal_declarations_path=root / "missing.json",
                    provider_scan_sentinel_path=sentinel,
                    scenario_path=scenario,
                    output_path=root / "status.json",
                    expected_cases=8,
                    minimum_pass_rate=0.8,
                )


if __name__ == "__main__":
    unittest.main()
