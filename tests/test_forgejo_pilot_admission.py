from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.native_admission import validate_native_scenario
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root
from scripts.build_forgejo_pilot_admission import (
    build_forgejo_pilot_admission,
)


class ForgejoPilotAdmissionTest(unittest.TestCase):
    def test_archived_native_pilot_is_truthfully_admitted_as_easy(self) -> None:
        root = repository_root()
        evidence = (
            root
            / "data"
            / "evidence"
            / "forgejo-native-recovery-control-20260729"
        )
        variants = (
            "merge_request_not_reached",
            "merge_committed_delivery_succeeded",
            "merge_committed_receiver_accepted_response_lost",
            "merge_committed_delivery_request_not_reached",
        )
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            baselines = temporary / "baselines"
            baselines.mkdir()
            for variant in variants:
                (baselines / f"compact_state_tree-{variant}.json").write_text(
                    json.dumps(
                        {
                            "baseline": "compact_state_tree",
                            "variant": variant,
                            "evaluation": {"passed": True},
                        }
                    ),
                    encoding="utf-8",
                )
            output = temporary / "scenario"
            build_forgejo_pilot_admission(
                blueprint_path=(
                    root
                    / "data"
                    / "scenario_blueprints"
                    / "forgejo-pr-release-dev-001"
                    / "scenario.json"
                ),
                prefix_path=evidence / "release-prefix.json",
                reference_directory=evidence / "raw",
                baseline_directory=baselines,
                output_directory=output,
            )
            report = validate_native_scenario(
                load_native_scenario(output / "scenario.json")
            )
            baseline_report = json.loads(
                (output / "artifacts" / "baselines.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertTrue(report.passed)
        self.assertEqual(report.admitted_tier, "easy")
        self.assertEqual(report.observed["successful_prefix_writes"], 15)
        self.assertEqual(report.observed["maximum_heuristic_pass_rate"], 1.0)
        self.assertIn(
            "compact_state_tree",
            baseline_report["matched_group_solvers"],
        )


if __name__ == "__main__":
    unittest.main()
