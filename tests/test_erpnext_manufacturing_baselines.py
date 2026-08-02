from __future__ import annotations

import unittest
from typing import Any

from aftermath_bench.integrations.erpnext_manufacturing_baselines import (
    BASELINE_NAMES,
    run_fixed_manufacturing_baseline,
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
                "document": {"name": "JC-CORR", "docstatus": self.corrective_docstatus},
            }
        if tool == "get_external_delivery":
            return {"ok": True, "delivered": True, "delivery": {"key": "JC-CORR"}}
        if tool == "find_background_jobs":
            return {"ok": True, "jobs": []}
        if tool == "create_manufacture_stock_entry":
            return {"ok": True, "document": {"name": "STE-FINAL"}}
        if tool == "create_quality_inspection":
            return {"ok": True, "document": {"name": "QI-FINAL"}}
        return {"ok": True}


PREFIX = {
    "corrective_job_card": "JC-CORR",
    "accepted_manufacture_stock_entry": "STE-ACCEPTED",
    "accepted_job_card": "JC-ACCEPTED",
    "rejected_job_card": "JC-REJECTED",
    "corrective_operation": "CALIBRATE",
    "quality_release_webhook": "QUALITY-RELEASE",
    "work_order": "WO-1",
    "rework_quantity": 2,
    "finished_item": "FG-1",
}


class ERPNextManufacturingBaselinesTest(unittest.TestCase):
    def test_every_declared_baseline_executes(self) -> None:
        for name in BASELINE_NAMES:
            with self.subTest(name=name):
                environment = _Environment()
                trace = run_fixed_manufacturing_baseline(
                    name,
                    environment=environment,  # type: ignore[arg-type]
                    prefix=PREFIX,
                )
                self.assertEqual(len(trace), len(environment.calls))

    def test_assume_committed_skips_boundary_investigation(self) -> None:
        environment = _Environment()
        run_fixed_manufacturing_baseline(
            "assume_committed",
            environment=environment,  # type: ignore[arg-type]
            prefix=PREFIX,
        )
        tools = [tool for tool, _arguments in environment.calls]
        self.assertEqual(
            tools,
            [
                "create_manufacture_stock_entry",
                "create_quality_inspection",
                "submit_document",
                "submit_document",
            ],
        )

    def test_failed_record_only_submits_draft_and_repairs_release(self) -> None:
        environment = _Environment(corrective_docstatus=0)
        run_fixed_manufacturing_baseline(
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
