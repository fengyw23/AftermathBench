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
        source_scenario = (
            repository_root()
            / "data"
            / "scenarios"
            / "erpnext-partial-return-holdout-001"
            / "scenario.json"
        )
        source_freeze = source_scenario.parent / "freeze.json"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = root / "scenario.json"
            freeze = root / "freeze.json"
            ledger = root / "usage-ledger.json"
            scenario.write_bytes(source_scenario.read_bytes())
            freeze.write_bytes(source_freeze.read_bytes())
            ledger.write_text(
                json.dumps(
                    {
                        "public_commitment_sha256": "commitment-001",
                        "events": [
                            {
                                "event": "consumed",
                                "details": {},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "not eligible"):
                verify_hidden_test_eligibility(
                    scenario_path=scenario,
                    freeze_path=freeze,
                    usage_ledger_path=ledger,
                )

    def test_new_frozen_hidden_test_is_eligible(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = root / "scenario.json"
            freeze = root / "freeze.json"
            ledger = root / "usage-ledger.json"
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
                        "public_commitment_sha256": "commitment-001",
                    }
                ),
                encoding="utf-8",
            )
            ledger.write_text(
                json.dumps(
                    {
                        "public_commitment_sha256": "commitment-001",
                        "events": [
                            {
                                "event": "frozen",
                                "details": {
                                    "public_commitment_sha256": (
                                        "commitment-001"
                                    )
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            result = verify_hidden_test_eligibility(
                scenario_path=scenario,
                freeze_path=freeze,
                usage_ledger_path=ledger,
            )
        self.assertTrue(all(result["checks"].values()))

    def test_active_freeze_is_rejected_after_model_access(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = root / "scenario.json"
            freeze = root / "freeze.json"
            ledger = root / "usage-ledger.json"
            scenario.write_text(
                json.dumps(
                    {
                        "scenario_id": "consumed-hidden-001",
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
                        "scenario_id": "consumed-hidden-001",
                        "status": "active",
                        "public_commitment_sha256": "commitment-002",
                    }
                ),
                encoding="utf-8",
            )
            ledger.write_text(
                json.dumps(
                    {
                        "public_commitment_sha256": "commitment-002",
                        "events": [
                            {
                                "event": "frozen",
                                "details": {
                                    "public_commitment_sha256": (
                                        "commitment-002"
                                    )
                                },
                            },
                            {
                                "event": "evaluation_locked",
                                "details": {
                                    "public_commitment_sha256": (
                                        "commitment-002"
                                    )
                                },
                            },
                            {
                                "event": "consumed",
                                "details": {
                                    "public_commitment_sha256": (
                                        "commitment-002"
                                    )
                                },
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "not eligible"):
                verify_hidden_test_eligibility(
                    scenario_path=scenario,
                    freeze_path=freeze,
                    usage_ledger_path=ledger,
                )


if __name__ == "__main__":
    unittest.main()
