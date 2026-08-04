from __future__ import annotations

import unittest
from typing import Any

from aftermath_bench.integrations.erpnext_shared_batch_baselines import (
    SHARED_BATCH_BASELINE_NAMES,
    run_fixed_shared_batch_baseline,
)


class _Environment:
    def __init__(self, *, corrective_docstatus: int = 1) -> None:
        self.corrective_docstatus = corrective_docstatus
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def invoke(self, tool: str, **arguments: Any) -> dict[str, Any]:
        self.calls.append((tool, arguments))
        if tool == "get_document":
            return {
                "ok": True,
                "document": {
                    "name": "JC-CORRECTIVE",
                    "docstatus": self.corrective_docstatus,
                },
            }
        if tool == "get_external_delivery":
            return {"ok": True, "delivered": True, "delivery": {"key": "CERT-1"}}
        if tool == "find_background_jobs":
            return {"ok": True, "jobs": []}
        if tool == "create_manufacture_stock_entry":
            return {"ok": True, "document": {"name": "STE-FINAL"}}
        if tool == "create_quality_inspection":
            return {"ok": True, "document": {"name": "QI-FINAL"}}
        return {"ok": True}


PREFIX = {
    "corrective_job_card": "JC-CORRECTIVE",
    "certificate_reference": "CERT-1",
    "certificate_webhook": "CERTIFICATE-HOOK",
    "primary_work_order": "WO-PRIMARY",
    "primary_finished_item": "FG-PRIMARY",
    "accepted_primary_manufacture": "STE-PRIMARY",
    "secondary_manufacture": "STE-SECONDARY",
    "shared_landed_cost_voucher": "LCV-1",
    "shared_purchase_receipt": "PR-1",
    "rejected_primary_job_card": "JC-REJECTED",
    "evaluation_fixture": {"operations": {"corrective": "CORRECTIVE-CALIBRATION"}},
    "rework_quantity": 3,
}


class ERPNextSharedBatchBaselinesTest(unittest.TestCase):
    def test_every_declared_baseline_executes(self) -> None:
        for name in SHARED_BATCH_BASELINE_NAMES:
            with self.subTest(name=name):
                environment = _Environment()
                trace = run_fixed_shared_batch_baseline(
                    name,
                    environment=environment,  # type: ignore[arg-type]
                    prefix=PREFIX,
                )
                self.assertEqual(len(trace), len(environment.calls))

    def test_assume_committed_skips_all_boundary_investigation(self) -> None:
        environment = _Environment()
        run_fixed_shared_batch_baseline(
            "assume_committed",
            environment=environment,  # type: ignore[arg-type]
            prefix=PREFIX,
        )
        self.assertEqual(
            [tool for tool, _arguments in environment.calls],
            [
                "create_manufacture_stock_entry",
                "create_quality_inspection",
                "submit_document",
                "submit_document",
            ],
        )

    def test_failed_record_only_does_not_complete_inventory(self) -> None:
        environment = _Environment(corrective_docstatus=0)
        run_fixed_shared_batch_baseline(
            "repair_failed_record_only",
            environment=environment,  # type: ignore[arg-type]
            prefix=PREFIX,
        )
        tools = [tool for tool, _arguments in environment.calls]
        self.assertIn("submit_document", tools)
        self.assertIn("get_external_delivery", tools)
        self.assertNotIn("create_manufacture_stock_entry", tools)


if __name__ == "__main__":
    unittest.main()
