from __future__ import annotations

import unittest

from aftermath_bench.native_erpnext_multiwarehouse_family import (
    ERP_NEXT_MULTIWAREHOUSE_FAMILY,
    ERP_NEXT_MULTIWAREHOUSE_TOOLS,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY


class NativeERPNextMultiwarehouseFamilyTests(unittest.TestCase):
    def test_family_is_registered(self) -> None:
        self.assertIs(
            NATIVE_FAMILY_REGISTRY.get("erpnext-multiwarehouse-transfer"),
            ERP_NEXT_MULTIWAREHOUSE_FAMILY,
        )

    def test_only_ordinary_native_tools_are_exposed(self) -> None:
        names = {tool.name for tool in ERP_NEXT_MULTIWAREHOUSE_TOOLS}
        self.assertIn("get_stock_balance", names)
        self.assertIn("create_second_transfer_leg", names)
        self.assertIn("create_stock_reservation_entry", names)
        self.assertNotIn("get_recovery_plan", names)
        self.assertNotIn("repair_multiwarehouse_transfer", names)
        self.assertNotIn("get_global_state_summary", names)

    def test_mutation_set_matches_public_tools(self) -> None:
        names = {tool.name for tool in ERP_NEXT_MULTIWAREHOUSE_TOOLS}
        self.assertTrue(ERP_NEXT_MULTIWAREHOUSE_FAMILY.mutation_tools <= names)


if __name__ == "__main__":
    unittest.main()
