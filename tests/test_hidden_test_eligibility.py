from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.hidden_test_eligibility import (
    begin_hidden_test_evaluation,
    consume_hidden_test_evaluation,
)
from aftermath_bench.native_freeze import append_usage_event, file_sha256
from aftermath_bench.schema import repository_root
from scripts.verify_hidden_test_eligibility import (
    verify_hidden_test_eligibility,
)


class HiddenTestEligibilityTest(unittest.TestCase):
    @staticmethod
    def _new_hidden_fixture(
        root: Path,
        *,
        scenario_id: str = "new-hidden-001",
        commitment: str = "commitment-001",
    ) -> tuple[Path, Path, Path]:
        scenario = root / "scenario.json"
        freeze = root / "freeze.json"
        ledger = root / "usage-ledger.json"
        scenario.write_text(
            json.dumps(
                {
                    "scenario_id": scenario_id,
                    "instance_spec_sha256": "instance-spec-sha",
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
                    "scenario_id": scenario_id,
                    "status": "active",
                    "public_commitment_sha256": commitment,
                    "scenario_sha256": file_sha256(scenario),
                    "instance_spec_semantic_sha256": "instance-spec-sha",
                }
            ),
            encoding="utf-8",
        )
        append_usage_event(
            ledger_path=ledger,
            event="frozen",
            details={"public_commitment_sha256": commitment},
        )
        return scenario, freeze, ledger

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
            commitment = "historical-commitment"
            append_usage_event(
                ledger_path=ledger,
                event="frozen",
                details={"public_commitment_sha256": commitment},
            )
            append_usage_event(
                ledger_path=ledger,
                event="evaluation_locked",
                details={"model": "historical"},
            )
            append_usage_event(
                ledger_path=ledger,
                event="consumed",
                details={},
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
            scenario, freeze, ledger = self._new_hidden_fixture(root)
            result = verify_hidden_test_eligibility(
                scenario_path=scenario,
                freeze_path=freeze,
                usage_ledger_path=ledger,
            )
        self.assertTrue(all(result["checks"].values()))

    def test_scenario_bytes_must_still_match_the_freeze(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario, freeze, ledger = self._new_hidden_fixture(root)
            payload = json.loads(scenario.read_text(encoding="utf-8"))
            payload["post_freeze_mutation"] = True
            scenario.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                RuntimeError,
                "scenario_bytes_match_freeze",
            ):
                verify_hidden_test_eligibility(
                    scenario_path=scenario,
                    freeze_path=freeze,
                    usage_ledger_path=ledger,
                )

    def test_runner_lock_is_atomic_resumable_and_consumable(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario, freeze, ledger = self._new_hidden_fixture(root)
            session = begin_hidden_test_evaluation(
                scenario_path=scenario,
                freeze_path=freeze,
                usage_ledger_path=ledger,
                evaluation_id="eval-001",
                provider="openai-compatible",
                model="test-model",
                execution_control=False,
            )
            resumed = begin_hidden_test_evaluation(
                scenario_path=scenario,
                freeze_path=freeze,
                usage_ledger_path=ledger,
                evaluation_id="eval-001",
                provider="openai-compatible",
                model="test-model",
                execution_control=False,
            )
            self.assertEqual(resumed, session)
            with self.assertRaisesRegex(
                RuntimeError,
                "not valid for provider access",
            ):
                begin_hidden_test_evaluation(
                    scenario_path=scenario,
                    freeze_path=freeze,
                    usage_ledger_path=ledger,
                    evaluation_id="different-evaluation",
                    provider="openai-compatible",
                    model="test-model",
                    execution_control=False,
                )
            consumed = consume_hidden_test_evaluation(
                scenario_path=scenario,
                freeze_path=freeze,
                session=session,
            )
            self.assertEqual(consumed["event"], "consumed")
            events = json.loads(ledger.read_text(encoding="utf-8"))["events"]
            self.assertEqual(
                [item["event"] for item in events],
                ["frozen", "evaluation_locked", "consumed"],
            )

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
            append_usage_event(
                ledger_path=ledger,
                event="frozen",
                details={"public_commitment_sha256": "commitment-002"},
            )
            append_usage_event(
                ledger_path=ledger,
                event="evaluation_locked",
                details={"model": "test"},
            )
            append_usage_event(
                ledger_path=ledger,
                event="consumed",
                details={},
            )

            with self.assertRaisesRegex(RuntimeError, "not eligible"):
                verify_hidden_test_eligibility(
                    scenario_path=scenario,
                    freeze_path=freeze,
                    usage_ledger_path=ledger,
                )

    def test_rewritten_usage_event_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = root / "scenario.json"
            freeze = root / "freeze.json"
            ledger = root / "usage-ledger.json"
            scenario.write_text(
                json.dumps(
                    {
                        "scenario_id": "hidden-001",
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
                        "scenario_id": "hidden-001",
                        "status": "active",
                        "public_commitment_sha256": "commitment-003",
                    }
                ),
                encoding="utf-8",
            )
            append_usage_event(
                ledger_path=ledger,
                event="frozen",
                details={"public_commitment_sha256": "commitment-003"},
            )
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            payload["events"][0]["details"]["rewritten"] = True
            ledger.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "not eligible"):
                verify_hidden_test_eligibility(
                    scenario_path=scenario,
                    freeze_path=freeze,
                    usage_ledger_path=ledger,
                )


if __name__ == "__main__":
    unittest.main()
