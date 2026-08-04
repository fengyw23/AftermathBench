from __future__ import annotations

import unittest
from typing import Any

from aftermath_bench.integrations.erpnext_shared_batch_evidence import (
    ERPNextSharedBatchEvidenceCollector,
)


class _Collector(ERPNextSharedBatchEvidenceCollector):
    def __init__(self) -> None:
        self.delivery_keys: list[str] = []

    def get_document(self, doctype: str, name: str) -> dict[str, Any]:
        return {"doctype": doctype, "name": name, "docstatus": 1}

    def full_documents(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | list[list[Any]] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if doctype == "Job Card":
            work_order = str(filters["work_order"])  # type: ignore[index]
            return [
                {
                    "doctype": doctype,
                    "name": f"job-{work_order}",
                    "work_order": work_order,
                    "docstatus": 1,
                }
            ]
        if doctype == "Stock Entry":
            work_order = str(filters["work_order"])  # type: ignore[index]
            return [
                {
                    "doctype": doctype,
                    "name": f"stock-{work_order}",
                    "work_order": work_order,
                    "docstatus": 1,
                }
            ]
        if doctype == "Quality Inspection":
            return [
                {"name": "quality-primary", "reference_name": "job-WO-PRIMARY"},
                {"name": "quality-secondary", "reference_name": "stock-WO-SECONDARY"},
                {"name": "quality-unrelated", "reference_name": "OTHER"},
            ]
        raise AssertionError(doctype)

    def list_documents(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | list[list[Any]] | None = None,
        fields: list[str] | None = None,
        order_by: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if doctype in {"Stock Ledger Entry", "GL Entry"}:
            return [
                {"name": "kept", "voucher_no": "PR-SHARED"},
                {"name": "dropped", "voucher_no": "UNRELATED"},
            ]
        raise AssertionError(doctype)

    def find_background_jobs(self, reference: str) -> list[dict[str, Any]]:
        if reference != "JC-CORRECTIVE":
            raise AssertionError(reference)
        return [{"name": "kept-job", "arguments": reference}]

    def get_delivery(self, key: str) -> dict[str, Any]:
        self.delivery_keys.append(key)
        return {"key": key, "attempt_count": 1}


class ERPNextSharedBatchEvidenceTest(unittest.TestCase):
    def test_collects_both_work_orders_and_filters_shared_vouchers(self) -> None:
        collector = _Collector()
        evidence = collector.collect(
            {
                "shared_purchase_receipt": "PR-SHARED",
                "shared_landed_cost_voucher": "LCV-SHARED",
                "primary_bom": "BOM-PRIMARY",
                "secondary_bom": "BOM-SECONDARY",
                "primary_work_order": "WO-PRIMARY",
                "secondary_work_order": "WO-SECONDARY",
                "primary_transfer": "STE-PRIMARY-TRANSFER",
                "secondary_transfer": "STE-SECONDARY-TRANSFER",
                "primary_material_quality_inspection": "QI-PRIMARY-MATERIAL",
                "secondary_material_quality_inspection": "QI-SECONDARY-MATERIAL",
                "accepted_primary_job_card": "JC-PRIMARY-ACCEPTED",
                "rejected_primary_job_card": "JC-PRIMARY-REJECTED",
                "secondary_job_card": "JC-SECONDARY",
                "accepted_primary_quality_inspection": "QI-PRIMARY-ACCEPTED",
                "rejected_quality_inspection": "QI-PRIMARY-REJECTED",
                "secondary_quality_inspection": "QI-SECONDARY-ACCEPTED",
                "accepted_primary_manufacture": "STE-PRIMARY-ACCEPTED",
                "secondary_manufacture": "STE-SECONDARY",
                "corrective_job_card": "JC-CORRECTIVE",
                "customer_reservation": "SO-CROSS-001",
                "stock_reservation_entry": "SRE-CROSS-001",
                "unrelated_receipt": "STE-UNRELATED",
                "supplier_batch_id": "SUP-BATCH-Z7-2408",
                "certificate_reference": "CERT-CORRECTIVE",
            }
        )
        self.assertEqual(
            {row["work_order"] for row in evidence["job_cards"]},
            {"WO-PRIMARY", "WO-SECONDARY"},
        )
        self.assertEqual(
            [row["name"] for row in evidence["quality_inspections"]],
            ["quality-primary", "quality-secondary"],
        )
        self.assertEqual(
            [row["name"] for row in evidence["stock_ledger_entries"]],
            ["kept"],
        )
        self.assertEqual([row["name"] for row in evidence["rq_jobs"]], ["kept-job"])
        self.assertEqual(collector.delivery_keys, ["CERT-CORRECTIVE"])


if __name__ == "__main__":
    unittest.main()
