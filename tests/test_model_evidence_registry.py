from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from aftermath_bench.model_evidence_registry import (
    ModelEvidenceRegistryError,
    load_model_evidence_registry,
    validate_model_evidence_registry,
)
from aftermath_bench.strict_json import load_json_strict


ROOT = Path(__file__).resolve().parents[1]


class ModelEvidenceRegistryTests(unittest.TestCase):
    def test_repository_registry_recomputes_correct_accounting(self) -> None:
        report = load_model_evidence_registry(ROOT / "data/model_evidence_registry.json", root=ROOT)
        self.assertTrue(report["passed"])
        self.assertEqual(report["counts"]["ordinary_model_tested_unique_state_count"], 29)
        self.assertEqual(report["counts"]["active_hard_ordinary_unique_state_count"], 25)
        self.assertEqual(
            report["counts"]["archived_hard_development_ordinary_unique_state_count"],
            4,
        )
        self.assertEqual(report["counts"]["current_formal_model_tested_unique_state_count"], 0)
        self.assertEqual(report["counts"]["control_only_unique_state_count"], 29)

    def test_multiple_models_do_not_duplicate_unique_states(self) -> None:
        report = load_model_evidence_registry(root=ROOT)
        package_r2 = [
            row
            for row in report["conditions"]
            if "30858985560" in row["condition_id"]
        ]
        self.assertEqual(len(package_r2), 2)
        self.assertEqual(
            len({(row["scenario_id"], variant) for row in package_r2 for variant in row["variant_ids"]}),
            4,
        )

    def test_control_cannot_be_promoted_to_ordinary(self) -> None:
        raw = copy.deepcopy(load_json_strict(ROOT / "data/model_evidence_registry.json"))
        control = next(item for item in raw["conditions"] if item["accounting_status"] == "control-only")
        control["accounting_status"] = "ordinary-model-tested"
        with self.assertRaisesRegex(ModelEvidenceRegistryError, "control cannot count as ordinary"):
            validate_model_evidence_registry(raw, root=ROOT)

    def test_identity_hash_change_is_rejected(self) -> None:
        raw = copy.deepcopy(load_json_strict(ROOT / "data/model_evidence_registry.json"))
        condition = raw["conditions"][0]
        condition["identity"]["tool_contract_sha256"] = "a" * 64
        with self.assertRaisesRegex(ModelEvidenceRegistryError, "identity hash differs"):
            validate_model_evidence_registry(raw, root=ROOT)


if __name__ == "__main__":
    unittest.main()
