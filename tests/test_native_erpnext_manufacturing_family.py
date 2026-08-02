from __future__ import annotations

import unittest

from aftermath_bench.native_erpnext_manufacturing_family import (
    ERP_NEXT_MANUFACTURING_FAMILY,
    ERP_NEXT_MANUFACTURING_TOOLS,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY


class NativeERPNextManufacturingFamilyTest(unittest.TestCase):
    def test_family_is_registered(self) -> None:
        self.assertIs(
            NATIVE_FAMILY_REGISTRY.get("erpnext-manufacturing-rework"),
            ERP_NEXT_MANUFACTURING_FAMILY,
        )

    def test_only_ordinary_native_tools_are_exposed(self) -> None:
        names = {tool.name for tool in ERP_NEXT_MANUFACTURING_TOOLS}
        self.assertIn("get_document", names)
        self.assertIn("create_manufacture_stock_entry", names)
        self.assertIn("create_quality_inspection", names)
        self.assertNotIn("get_recovery_plan", names)
        self.assertNotIn("repair_manufacturing_workflow", names)
        self.assertNotIn("get_global_state_summary", names)

    def test_mutation_set_matches_public_tools(self) -> None:
        names = {tool.name for tool in ERP_NEXT_MANUFACTURING_TOOLS}
        self.assertTrue(ERP_NEXT_MANUFACTURING_FAMILY.mutation_tools <= names)


if __name__ == "__main__":
    unittest.main()
