from __future__ import annotations

import unittest

from aftermath_bench.native_erpnext_shared_batch_family import (
    ERP_NEXT_SHARED_BATCH_FAMILY,
    ERP_NEXT_SHARED_BATCH_TOOLS,
    shared_batch_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root


class NativeERPNextSharedBatchFamilyTest(unittest.TestCase):
    def setUp(self) -> None:
        root = repository_root()
        self.scenario = load_native_scenario(
            root
            / "data"
            / "scenario_blueprints"
            / "erpnext-shared-batch-recovery-dev-001"
            / "scenario.json"
        )

    def test_family_is_registered_and_mutations_are_public(self) -> None:
        self.assertIs(
            NATIVE_FAMILY_REGISTRY.get("erpnext-shared-batch-recovery"),
            ERP_NEXT_SHARED_BATCH_FAMILY,
        )
        tool_names = {tool.name for tool in ERP_NEXT_SHARED_BATCH_TOOLS}
        self.assertTrue(ERP_NEXT_SHARED_BATCH_FAMILY.mutation_tools <= tool_names)

    def test_document_tools_expose_cross_obligation_native_types(self) -> None:
        get_document = next(
            tool for tool in ERP_NEXT_SHARED_BATCH_TOOLS if tool.name == "get_document"
        )
        doctypes = set(get_document.input_schema["properties"]["doctype"]["enum"])
        self.assertTrue(
            {
                "Purchase Receipt",
                "Landed Cost Voucher",
                "Sales Order",
                "Stock Reservation Entry",
            }.issubset(doctypes)
        )

    def test_initial_message_does_not_expose_evaluator_only_state(self) -> None:
        prefix = {
            "company": "Aftermath Laboratories LLC",
            "shared_component": "SENSOR-ARRAY-Z7",
            "supplier_batch_id": "SUP-BATCH-Z7-2408",
            "shared_purchase_receipt": "PR-1",
            "shared_landed_cost_voucher": "LCV-1",
            "primary_work_order": "WO-P",
            "secondary_work_order": "WO-S",
            "accepted_primary_manufacture": "STE-P9",
            "secondary_manufacture": "STE-S8",
            "corrective_job_card": "JC-C",
            "customer_reservation": "SO-CROSS-001",
            "stock_reservation_entry": "SRE-1",
            "unrelated_receipt": "STE-U",
            "certificate_reference": "cert-1",
            "certificate_webhook": "Webhook 1",
            "accepted_quantity": 9,
            "rework_quantity": 3,
            "secondary_quantity": 8,
            "evaluation_fixture": {"hidden": "not-model-input"},
            "protected_fingerprints": {"hidden": "not-model-input"},
            "trace": [{"tool": "submit Purchase Receipt", "status": "success"}],
        }
        message = shared_batch_initial_message(
            scenario=self.scenario,
            prefix=prefix,
            failure_report={
                "latest_attempt": {
                    "tool": "submit_document",
                    "result": {"error": "connection_lost_before_confirmation"},
                }
            },
        )
        self.assertIn("SUP-BATCH-Z7-2408", message)
        self.assertIn("connection_lost_before_confirmation", message)
        self.assertNotIn("not-model-input", message)
        self.assertNotIn("protected_fingerprints", message)


if __name__ == "__main__":
    unittest.main()
