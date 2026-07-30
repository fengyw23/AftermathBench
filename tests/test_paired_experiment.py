from __future__ import annotations

import unittest

from aftermath_bench.paired_experiment import compare_paired_experiments


def _metadata(*, control: bool, rate: float) -> dict:
    return {
        "scenario_id": "scenario-1",
        "head_sha": "a" * 40,
        "model": "model-1",
        "execution_control": control,
        "control_min_pass_rate": 0.8,
        "credentials_present": False,
        "completed_runs": 4,
        "task_pass_rate": rate,
        "matched_group_success_rate": float(rate == 1.0),
        "provider_or_runtime_error_count": 0,
        "tool_error_count": 0,
        "supporting_files": {"prefix.json": "b" * 64},
        "reports": [{"variant": f"state_{index}"} for index in range(4)],
    }


class PairedExperimentTest(unittest.TestCase):
    def test_accepts_valid_pair_and_computes_gap(self) -> None:
        result = compare_paired_experiments(
            _metadata(control=True, rate=1.0),
            _metadata(control=False, rate=0.5),
        )
        self.assertTrue(result["valid_pair"])
        self.assertEqual(result["absolute_control_gap"], 0.5)
        self.assertEqual(len(result["variants"]), 4)

    def test_rejects_source_or_prefix_mismatch(self) -> None:
        control = _metadata(control=True, rate=1.0)
        ordinary = _metadata(control=False, rate=0.5)
        ordinary["head_sha"] = "c" * 40
        ordinary["supporting_files"]["prefix.json"] = "d" * 64
        result = compare_paired_experiments(control, ordinary)
        self.assertFalse(result["valid_pair"])
        self.assertFalse(result["checks"]["source_commit_matches"])
        self.assertFalse(result["checks"]["prefix_matches"])

    def test_rejects_control_below_threshold(self) -> None:
        result = compare_paired_experiments(
            _metadata(control=True, rate=0.75),
            _metadata(control=False, rate=0.5),
        )
        self.assertFalse(result["valid_pair"])
        self.assertFalse(
            result["checks"]["control_meets_execution_threshold"]
        )


if __name__ == "__main__":
    unittest.main()
