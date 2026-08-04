from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.frozen_hidden_registry import load_frozen_hidden_registry


ROOT = Path(__file__).resolve().parents[1]


class FrozenHiddenRegistryTests(unittest.TestCase):
    def test_repository_registry_proves_unseen_hard_slots(self) -> None:
        records = load_frozen_hidden_registry(
            ROOT / "data" / "frozen_hidden_candidates.json",
            root=ROOT,
        )
        self.assertGreaterEqual(len(records), 4)
        self.assertGreaterEqual(
            sum(item.variant_count for item in records),
            16,
        )
        self.assertEqual(
            {item.instance_id for item in records},
            {"test-001", "test-002"},
        )
        self.assertEqual(len({item.freeze_run_id for item in records}), len(records))

    def test_tampered_receipt_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "receipt.json"
            evidence.write_text("{}\n", encoding="utf-8")
            registry = {
                "schema_version": "1.0",
                "records": [
                    {
                        "formal_slot_id": "erpnext/family/test-001",
                        "scenario_id": "scenario",
                        "domain_id": "erpnext",
                        "family_id": "family",
                        "instance_id": "test-001",
                        "variant_count": 4,
                        "freeze_run_id": 1,
                        "public_commitment_sha256": "a" * 64,
                        "artifact_url": "https://github.com/example/run/1",
                        "evidence_path": "receipt.json",
                        "evidence_sha256": "b" * 64,
                    }
                ],
            }
            path = root / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "record 0 is invalid"):
                load_frozen_hidden_registry(path, root=root)


if __name__ == "__main__":
    unittest.main()
