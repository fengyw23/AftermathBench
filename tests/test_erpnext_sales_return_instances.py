from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from aftermath_bench.integrations.erpnext_sales_return_instance import (
    ERPNextSalesReturnInstanceSpec,
    sales_return_blueprint,
)
from aftermath_bench.schema import repository_root
from aftermath_bench.strict_json import load_json_strict


class ERPNextSalesReturnInstanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = repository_root()
        self.spec_path = (
            self.root
            / "data"
            / "instance_specs"
            / "erpnext-sales-return-public-dev-001.json"
        )
        self.blueprint_path = (
            self.root
            / "data"
            / "scenario_blueprints"
            / "erpnext-sales-return-public-dev-001"
            / "scenario.json"
        )

    def test_checked_blueprint_is_exactly_rendered_from_instance(self) -> None:
        instance = ERPNextSalesReturnInstanceSpec.from_path(self.spec_path)
        expected = sales_return_blueprint(
            instance,
            instance_id="dev-001",
            benchmark_split="public_dev",
        )
        self.assertEqual(load_json_strict(self.blueprint_path), expected)
        self.assertEqual(
            expected["instance_spec_sha256"],
            "e2995fe40ae298e77c7835573f3ec598d6b7452f035452d5ca934e0a3f7d82f3",
        )
        self.assertEqual(
            expected["benchmark_split"],
            "public_dev",
        )
        self.assertFalse(expected["hidden_test_eligible"])
        self.assertEqual(len(expected["matched_variants"]), 4)
        self.assertEqual(
            len(expected["required_semantic_recovery_directions"]),
            4,
        )

    def test_public_instance_does_not_reuse_consumed_business_identity(self) -> None:
        current = ERPNextSalesReturnInstanceSpec.from_path(self.spec_path)
        consumed = load_json_strict(
            self.root
            / "data"
            / "scenarios"
            / "erpnext-sales-return-dev-001"
            / "scenario.json"
        )["fixture"]
        current_codes = {
            current.affected_item["item_code"],
            current.unaffected_item["item_code"],
            current.replacement_item["item_code"],
        }
        consumed_codes = {
            consumed["affected_item"]["item_code"],
            consumed["unaffected_item"]["item_code"],
            consumed["replacement_item"]["item_code"],
        }
        self.assertNotEqual(current.customer, consumed["customer"])
        self.assertTrue(current_codes.isdisjoint(consumed_codes))

    def test_rejects_economically_or_quantitatively_invalid_exchange(self) -> None:
        raw = json.loads(self.spec_path.read_text(encoding="utf-8"))
        invalid_quantity = copy.deepcopy(raw)
        invalid_quantity["replacement_item"]["quantity"] = 2
        with self.assertRaisesRegex(
            ValueError,
            "quantities or prices",
        ):
            ERPNextSalesReturnInstanceSpec.from_dict(invalid_quantity)

        invalid_price = copy.deepcopy(raw)
        invalid_price["replacement_item"]["unit_price"] = 1
        with self.assertRaisesRegex(
            ValueError,
            "quantities or prices",
        ):
            ERPNextSalesReturnInstanceSpec.from_dict(invalid_price)


if __name__ == "__main__":
    unittest.main()
