from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from aftermath_bench.native_erpnext_multiwarehouse_family import (
    ERP_NEXT_MULTIWAREHOUSE_FAMILY,
    ERP_NEXT_MULTIWAREHOUSE_TOOLS,
    diagnose_multiwarehouse_trajectory,
    multiwarehouse_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_scenario import NativeScenario


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

    def test_execution_control_uses_instance_reservation_and_warehouse(self) -> None:
        prefix = {
            key: key
            for key in (
                "company",
                "transfer_item",
                "transfer_quantity",
                "batch_id",
                "source_warehouse",
                "transit_warehouse",
                "destination_warehouse",
                "material_request",
                "outgoing_stock_entry",
                "second_leg_stock_entry",
                "clinic_sales_order",
                "protected_sales_order",
                "protected_reservation",
                "arrival_webhook",
            )
        }
        prefix.update(
            {
                "protected_warehouse": "Emergency Reserve - AL",
                "clinic_reserved_quantity": 6,
                "trace": [],
            }
        )
        message = multiwarehouse_initial_message(
            scenario=NativeScenario(
                Path("scenario.json"), {"user_instruction": "do it"}
            ),
            prefix=prefix,
            failure_report={"latest_attempt": {}},
            execution_control=True,
        )
        self.assertIn("Emergency Reserve - AL", message)
        self.assertIn("one 6-unit reservation", message)
        self.assertNotIn("North emergency", message)

    def test_diagnostics_read_the_current_trajectory_schema(self) -> None:
        report = diagnose_multiwarehouse_trajectory(
            turns=[
                {
                    "tool_calls": [
                        {"name": "list_documents"},
                        {"name": "get_stock_ledger"},
                        {"name": "get_stock_balance"},
                        {"name": "get_external_delivery"},
                    ]
                }
            ],
            evaluation=SimpleNamespace(
                passed=False,
                components={
                    "goal_completion": False,
                    "repair_completeness": False,
                    "preservation": True,
                },
            ),
            failure_report={},
            prefix={},
        )
        self.assertEqual(report["tool_names"][0], "list_documents")
        self.assertNotIn("investigation_failure", report["all"])

    def test_success_is_not_relabelled_as_an_investigation_failure(self) -> None:
        report = diagnose_multiwarehouse_trajectory(
            turns=[],
            evaluation=SimpleNamespace(passed=True, components={}),
            failure_report={},
            prefix={},
        )
        self.assertEqual(report["primary"], "success")


if __name__ == "__main__":
    unittest.main()
