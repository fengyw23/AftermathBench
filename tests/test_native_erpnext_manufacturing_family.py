from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from aftermath_bench.native_erpnext_manufacturing_family import (
    ERP_NEXT_MANUFACTURING_FAMILY,
    ERP_NEXT_MANUFACTURING_TOOLS,
    diagnose_manufacturing_trajectory,
    manufacturing_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_scenario import NativeScenario


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

    def test_execution_control_uses_instance_quantities(self) -> None:
        prefix = {
            key: key
            for key in (
                "company",
                "work_order",
                "bom",
                "finished_item",
                "accepted_job_card",
                "rejected_job_card",
                "corrective_job_card",
                "accepted_manufacture_stock_entry",
                "quality_release_webhook",
            )
        }
        prefix.update({"accepted_quantity": 11, "rework_quantity": 3, "trace": []})
        message = manufacturing_initial_message(
            scenario=NativeScenario(
                Path("scenario.json"), {"user_instruction": "do it"}
            ),
            prefix=prefix,
            failure_report={"latest_attempt": {}},
            execution_control=True,
        )
        self.assertIn("11-unit manufacture entry", message)
        self.assertIn("remaining 3-unit", message)
        self.assertNotIn("eight-unit", message)

    def test_diagnostics_read_the_current_trajectory_schema(self) -> None:
        report = diagnose_manufacturing_trajectory(
            turns=[
                {
                    "tool_calls": [
                        {"name": "get_document"},
                        {"name": "find_background_jobs"},
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
        self.assertEqual(report["tool_names"][0], "get_document")
        self.assertNotIn("investigation_failure", report["all"])

    def test_success_is_not_relabelled_as_an_investigation_failure(self) -> None:
        report = diagnose_manufacturing_trajectory(
            turns=[],
            evaluation=SimpleNamespace(passed=True, components={}),
            failure_report={},
            prefix={},
        )
        self.assertEqual(report["primary"], "success")


if __name__ == "__main__":
    unittest.main()
