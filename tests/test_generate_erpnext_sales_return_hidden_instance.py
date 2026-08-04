from __future__ import annotations

import unittest

from scripts.generate_erpnext_sales_return_hidden_instance import build_instance
from aftermath_bench.integrations.erpnext_sales_return_instance import (
    ERPNextSalesReturnInstanceSpec,
)


class GenerateERPNextSalesReturnHiddenInstanceTests(unittest.TestCase):
    def test_generated_instance_satisfies_the_native_schema(self) -> None:
        instance = ERPNextSalesReturnInstanceSpec.from_dict(
            build_instance("test-001")
        )
        self.assertIn("hidden-test-001", instance.scenario_id)
        self.assertEqual(
            instance.replacement_item["quantity"],
            instance.affected_item["defective_quantity"],
        )
        self.assertEqual(
            instance.replacement_item["unit_price"],
            instance.affected_item["unit_price"],
        )

    def test_each_instance_gets_a_fresh_private_identity(self) -> None:
        first = build_instance("test-001")
        second = build_instance("test-002")
        self.assertNotEqual(first["scenario_id"], second["scenario_id"])
        self.assertNotEqual(
            first["affected_item"]["item_code"],
            second["affected_item"]["item_code"],
        )


if __name__ == "__main__":
    unittest.main()
