from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.verify_hidden_consumption_registry import (
    assert_unconsumed,
    validate_registry,
)


ROOT = Path(__file__).resolve().parents[1]


class HiddenEvaluationRegistryTests(unittest.TestCase):
    def test_repository_registry_is_valid_and_records_test_003(self) -> None:
        records = validate_registry(
            ROOT / "data" / "hidden_evaluation_registry.json",
            root=ROOT,
        )
        test_003 = next(
            record
            for record in records
            if record["scenario_id"]
            == "erpnext-manufacturing-rework-hidden-test-003"
        )
        self.assertEqual(test_003["disposition"], "consumed")
        self.assertEqual(test_003["freeze_run_id"], 30804648059)

    def test_terminal_commitment_or_freeze_run_is_rejected(self) -> None:
        records = validate_registry(
            ROOT / "data" / "hidden_evaluation_registry.json",
            root=ROOT,
        )
        with self.assertRaisesRegex(RuntimeError, "must never be evaluated again"):
            assert_unconsumed(
                records,
                public_commitment_sha256=(
                    "2e01eb0a0bc5c4ac06a7f35558287ea14cab4e1a3fe0da0fbd2092b6664e0b14"
                ),
                freeze_run_id=999,
            )
        with self.assertRaises(RuntimeError):
            assert_unconsumed(
                records,
                public_commitment_sha256="f" * 64,
                freeze_run_id=30804648059,
            )

    def test_unseen_candidate_is_accepted(self) -> None:
        records = validate_registry(
            ROOT / "data" / "hidden_evaluation_registry.json",
            root=ROOT,
        )
        assert_unconsumed(
            records,
            public_commitment_sha256="f" * 64,
            freeze_run_id=99999999999,
        )

    def test_duplicate_commitment_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence.json"
            evidence.write_text("{}\n", encoding="utf-8")
            record = {
                "scenario_id": "hidden-1",
                "public_commitment_sha256": "a" * 64,
                "freeze_run_id": 1,
                "evaluation_run_id": 2,
                "disposition": "consumed",
                "evidence_path": "evidence.json",
            }
            registry = root / "registry.json"
            registry.write_text(
                json.dumps(
                    {"schema_version": "1.0", "records": [record, record]}
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "identities must be unique"):
                validate_registry(registry, root=root)


if __name__ == "__main__":
    unittest.main()
