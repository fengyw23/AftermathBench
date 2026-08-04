from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.model_coverage_assembly import (
    TrajectorySource,
    assemble_model_coverage,
)


def _write(
    root: Path,
    variant: str,
    *,
    passed: bool,
    execution_control: bool = False,
) -> None:
    path = root / "repetition-01" / f"{variant}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "scenario_id": "scenario-1",
                "variant": variant,
                "execution_control": execution_control,
                "evaluation": {"passed": passed},
            }
        ),
        encoding="utf-8",
    )


class ModelCoverageAssemblyTest(unittest.TestCase):
    def test_retry_only_fills_missing_primary_trajectory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary = root / "primary"
            retry = root / "retry"
            output = root / "combined"
            _write(primary, "state_01", passed=False)
            _write(retry, "state_02", passed=True)

            manifest = assemble_model_coverage(
                primary=TrajectorySource("run-1", primary, "primary"),
                retries=[TrajectorySource("run-2", retry, "provider_retry")],
                expected_variants={"state_01", "state_02"},
                output_root=output,
            )

            self.assertEqual(manifest["trajectory_count"], 2)
            self.assertEqual(manifest["missing_primary_variants"], ["state_02"])
            self.assertTrue((output / "repetition-01" / "state_02.json").is_file())
            sources = {
                row["variant"]: row["source_run_id"] for row in manifest["trajectories"]
            }
            self.assertEqual(sources, {"state_01": "run-1", "state_02": "run-2"})
            self.assertTrue(
                all(
                    not Path(row["source_path"]).is_absolute()
                    for row in manifest["trajectories"]
                )
            )

    def test_retry_cannot_replace_scored_primary_trajectory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary = root / "primary"
            retry = root / "retry"
            _write(primary, "state_01", passed=False)
            _write(retry, "state_01", passed=True)
            with self.assertRaisesRegex(ValueError, "replace or duplicate"):
                assemble_model_coverage(
                    primary=TrajectorySource("run-1", primary, "primary"),
                    retries=[TrajectorySource("run-2", retry, "provider_retry")],
                    expected_variants={"state_01"},
                    output_root=root / "combined",
                )

    def test_incomplete_retry_coverage_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary = root / "primary"
            _write(primary, "state_01", passed=True)
            with self.assertRaisesRegex(ValueError, "did not complete coverage"):
                assemble_model_coverage(
                    primary=TrajectorySource("run-1", primary, "primary"),
                    retries=[],
                    expected_variants={"state_01", "state_02"},
                    output_root=root / "combined",
                )

    def test_retry_cannot_change_execution_control_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary = root / "primary"
            retry = root / "retry"
            _write(primary, "state_01", passed=True)
            _write(retry, "state_02", passed=True, execution_control=True)
            with self.assertRaisesRegex(ValueError, "execution-control mode"):
                assemble_model_coverage(
                    primary=TrajectorySource("run-1", primary, "primary"),
                    retries=[TrajectorySource("run-2", retry, "provider_retry")],
                    expected_variants={"state_01", "state_02"},
                    output_root=root / "combined",
                )


if __name__ == "__main__":
    unittest.main()
