from __future__ import annotations

import unittest

from aftermath_bench.native_erpnext_inventory_cost_family import (
    ERP_NEXT_INVENTORY_COST_FAMILY,
    ERP_NEXT_INVENTORY_COST_TOOLS,
    inventory_cost_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root


class NativeERPNextInventoryCostFamilyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = load_native_scenario(
            repository_root()
            / "data"
            / "scenario_blueprints"
            / "erpnext-inventory-cost-settlement-public-dev-001"
            / "scenario.json"
        )
        self.prefix = {
            "company": "Aftermath Laboratories LLC",
            "shared_component": "SENSOR-MODULE-R8",
            "supplier_batch_id": "SUP-BATCH-R8-2608",
            "shared_purchase_receipt": "PR-1",
            "primary_work_order": "WO-1",
            "secondary_work_order": "WO-2",
            "primary_manufacture": "STE-1",
            "secondary_manufacture": "STE-2",
            "customer_reservation": "SO-1",
            "stock_reservation_entry": "SRE-1",
            "unrelated_receipt": "STE-U",
            "landed_cost_voucher": "LCV-1",
            "settlement_webhook": "settlement",
            "attestation_reference": "attestation-key",
            "trace": [],
        }
        self.failure = {
            "latest_attempt": {
                "tool": "submit_document",
                "arguments": {"doctype": "Landed Cost Voucher", "name": "LCV-1"},
                "result": {"ok": False, "error": "connection lost"},
            }
        }

    def test_family_is_registered_with_non_answer_tools(self) -> None:
        self.assertIs(
            NATIVE_FAMILY_REGISTRY.get("erpnext-inventory-cost-settlement"),
            ERP_NEXT_INVENTORY_COST_FAMILY,
        )
        names = {tool.name for tool in ERP_NEXT_INVENTORY_COST_TOOLS}
        self.assertEqual(names, set(ERP_NEXT_INVENTORY_COST_FAMILY.mutation_tools) | {
            "get_document",
            "list_documents",
            "get_stock_ledger",
            "get_general_ledger",
            "find_background_jobs",
            "get_external_delivery",
            "wait_for_external_delivery",
        })
        self.assertNotIn("recommended_action", names)
        self.assertNotIn("inspect_inventory_cost_state", names)

    def test_prompt_shows_common_failure_not_hidden_variant(self) -> None:
        message = inventory_cost_initial_message(
            scenario=self.scenario,
            prefix=self.prefix,
            failure_report=self.failure,
        )
        self.assertIn("connection lost", message)
        self.assertIn("LCV-1", message)
        self.assertNotIn("request_not_reached", message)
        self.assertNotIn("voucher_committed", message)


if __name__ == "__main__":
    unittest.main()
