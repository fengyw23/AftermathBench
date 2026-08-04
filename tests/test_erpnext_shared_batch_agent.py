from __future__ import annotations

import copy
import unittest
from typing import Any

from aftermath_bench.integrations.erpnext_shared_batch_agent import (
    ERPNextSharedBatchEnvironment,
)


class _Adapter:
    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None

    def call_method(self, method: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "message": {
                "doctype": "Stock Entry",
                "items": [
                    {
                        "item_code": "SENSOR-ARRAY-Z7",
                        "serial_and_batch_bundle": "OLD",
                    },
                    {"item_code": "CARDIAC-MONITOR-Z7"},
                ],
            }
        }

    def create_resource(self, doctype: str, document: dict[str, Any]) -> dict[str, Any]:
        self.created = copy.deepcopy(document)
        return {"data": {**document, "doctype": doctype, "name": "STE-CORRECTIVE"}}


class ERPNextSharedBatchAgentTest(unittest.TestCase):
    def test_corrective_manufacture_uses_the_existing_supplier_batch(self) -> None:
        adapter = _Adapter()
        environment = object.__new__(ERPNextSharedBatchEnvironment)
        environment.adapter = adapter  # type: ignore[assignment]
        environment.prefix = {  # type: ignore[assignment]
            "shared_component": "SENSOR-ARRAY-Z7",
            "supplier_batch_id": "SUP-BATCH-Z7-2408",
        }
        result = environment._create_manufacture_stock_entry("WO-P", 3)
        self.assertTrue(result["ok"])
        shared = adapter.created["items"][0]  # type: ignore[index]
        self.assertEqual(shared["batch_no"], "SUP-BATCH-Z7-2408")
        self.assertEqual(shared["use_serial_batch_fields"], 1)
        self.assertNotIn("serial_and_batch_bundle", shared)

    def test_public_reads_cover_every_cross_obligation_document(self) -> None:
        self.assertTrue(
            {
                "Purchase Receipt",
                "Landed Cost Voucher",
                "Sales Order",
                "Stock Reservation Entry",
            }.issubset(ERPNextSharedBatchEnvironment.ALLOWED_DOCUMENT_TYPES)
        )

    def test_background_job_query_uses_native_operational_bridge(self) -> None:
        class Collector:
            def find_background_jobs(self, reference: str):
                return [{"name": "job-1", "status": "queued", "ref": reference}]

        environment = object.__new__(ERPNextSharedBatchEnvironment)
        environment.collector = Collector()  # type: ignore[assignment]
        result = environment._find_jobs("PO-JOB00004")
        self.assertTrue(result["ok"])
        self.assertEqual(result["jobs"][0]["ref"], "PO-JOB00004")


if __name__ == "__main__":
    unittest.main()
