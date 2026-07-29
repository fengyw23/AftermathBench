from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.schema import repository_root
from scripts.verify_hidden_test_eligibility import (
    verify_hidden_test_eligibility,
)


class HiddenTestEligibilityTest(unittest.TestCase):
    def test_consumed_historical_holdout_is_rejected(self) -> None:
        scenario = (
            repository_root()
            / "data"
            / "scenarios"
            / "erpnext-partial-return-holdout-001"
            / "scenario.json"
        )
        freeze = scenario.parent / "freeze.json"
        with self.assertRaisesRegex(RuntimeError, "not eligible"):
            verify_hidden_test_eligibility(
                scenario_path=scenario,
                freeze_path=freeze,
            )

    def test_new_frozen_hidden_test_is_eligible(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = root / "scenario.json"
            freeze = root / "freeze.json"
            scenario.write_text(
                json.dumps(
                    {
                        "scenario_id": "new-hidden-001",
                        "benchmark_split": "hidden_test",
                        "benchmark_tier": "hard",
                        "evaluation_status": {
                            "hidden_test_eligible": True,
                        },
                    }
                ),
                encoding="utf-8",
            )
            freeze.write_text(
                json.dumps(
                    {
                        "scenario_id": "new-hidden-001",
                        "status": "active",
                    }
                ),
                encoding="utf-8",
            )
            result = verify_hidden_test_eligibility(
                scenario_path=scenario,
                freeze_path=freeze,
            )
        self.assertTrue(all(result["checks"].values()))


if __name__ == "__main__":
    unittest.main()
