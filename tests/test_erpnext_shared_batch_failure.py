from __future__ import annotations

import unittest

from scripts.run_erpnext_shared_batch_failure import (
    SHARED_BATCH_VARIANTS,
    ensure_native_pending_certificate_job,
    validate_shared_batch_boundary,
)
from aftermath_bench.integrations.erpnext_shared_batch_evaluator import (
    shared_batch_document_fingerprint,
)


class ERPNextSharedBatchFailureTest(unittest.TestCase):
    def evidence(self, *, submitted: bool, delivered: bool) -> tuple[dict, dict]:
        protected = {
            key: {"doctype": doctype, "name": f"DOC-{index}", "docstatus": 1}
            for index, (key, doctype) in enumerate(
                (
                    ("shared_purchase_receipt", "Purchase Receipt"),
                    ("primary_bom", "BOM"),
                    ("secondary_bom", "BOM"),
                    ("primary_transfer", "Stock Entry"),
                    ("secondary_transfer", "Stock Entry"),
                    ("primary_material_quality_inspection", "Quality Inspection"),
                    ("secondary_material_quality_inspection", "Quality Inspection"),
                    ("accepted_primary_job_card", "Job Card"),
                    ("rejected_primary_job_card", "Job Card"),
                    ("secondary_job_card", "Job Card"),
                    ("accepted_primary_quality_inspection", "Quality Inspection"),
                    ("rejected_quality_inspection", "Quality Inspection"),
                    ("secondary_quality_inspection", "Quality Inspection"),
                ),
                start=1,
            )
        }
        protected.update(
            {
                "accepted_primary_manufacture": {
                    "doctype": "Stock Entry",
                    "name": "STE-P9",
                    "docstatus": 1,
                },
                "secondary_manufacture": {
                    "doctype": "Stock Entry",
                    "name": "STE-S8",
                    "docstatus": 1,
                },
                "customer_reservation": {
                    "doctype": "Sales Order",
                    "name": "SO-CROSS-001",
                    "docstatus": 1,
                },
                "shared_landed_cost_voucher": {
                    "doctype": "Landed Cost Voucher",
                    "name": "LCV-1",
                    "docstatus": 1,
                },
                "unrelated_receipt": {
                    "doctype": "Stock Entry",
                    "name": "STE-U",
                    "docstatus": 1,
                },
            }
        )
        prefix = {
            "corrective_job_card": "JC-C",
            "certificate_webhook": "CERTIFICATE-HOOK",
            "primary_work_order": "WO-P",
            "accepted_primary_manufacture": "STE-P9",
            "accepted_quantity": 9,
            "secondary_quantity": 8,
            "expected_corrective_operation_cost": 144,
            "protected_fingerprints": {
                key: shared_batch_document_fingerprint(document)
                for key, document in protected.items()
            },
        }
        evidence = {
            **protected,
            "corrective_job_card": {"name": "JC-C", "docstatus": int(submitted)},
            "primary_work_order": {
                "name": "WO-P",
                "produced_qty": 9,
                "corrective_operation_cost": 144 if submitted else 0,
            },
            "secondary_work_order": {"name": "WO-S", "produced_qty": 8},
            "stock_reservation_entry": {"docstatus": 1, "reserved_qty": 8},
            "manufacture_stock_entries": [
                {
                    "name": "STE-P9",
                    "work_order": "WO-P",
                    "purpose": "Manufacture",
                    "docstatus": 1,
                }
            ],
            "rq_jobs": [],
            "certificate_delivery": (
                {"key": "certificate", "attempt_count": 1} if delivered else None
            ),
        }
        return prefix, evidence

    def test_pending_variant_uses_native_enqueue_only_when_hook_is_absent(self) -> None:
        class _Stack:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def enqueue_document_webhook(self, **kwargs: object) -> dict:
                self.calls.append(dict(kwargs))
                return {"job_id": "job-1"}

        prefix, evidence = self.evidence(submitted=True, delivered=False)
        stack = _Stack()
        result = ensure_native_pending_certificate_job(
            "job_card_committed_certificate_job_pending",
            evidence,
            prefix,
            stack,  # type: ignore[arg-type]
        )
        self.assertEqual(result["action"], "native_enqueue_replayed")  # type: ignore[index]
        self.assertEqual(len(stack.calls), 1)
        evidence["rq_jobs"] = [
            {
                "status": "queued",
                "arguments": '{"name":"JC-C"}',
            }
        ]
        result = ensure_native_pending_certificate_job(
            "job_card_committed_certificate_job_pending",
            evidence,
            prefix,
            stack,  # type: ignore[arg-type]
        )
        self.assertEqual(result, {"action": "automatic_hook_observed"})
        self.assertEqual(len(stack.calls), 1)

    def test_public_variants_map_to_four_source_supported_faults(self) -> None:
        self.assertEqual(len(SHARED_BATCH_VARIANTS), 4)
        self.assertEqual(len(set(SHARED_BATCH_VARIANTS.values())), 4)

    def test_accepts_request_not_reached_boundary(self) -> None:
        prefix, evidence = self.evidence(submitted=False, delivered=False)
        result = validate_shared_batch_boundary(
            "request_not_reached",
            evidence,
            prefix,
            [
                {
                    "method": "POST",
                    "path": "/api/method/frappe.client.submit",
                    "outcome": "request_suppressed",
                    "upstream_status": None,
                }
            ],
        )
        self.assertTrue(result["passed"], result)

    def test_accepts_committed_and_delivered_boundary(self) -> None:
        prefix, evidence = self.evidence(submitted=True, delivered=True)
        result = validate_shared_batch_boundary(
            "job_card_committed_certificate_delivered_response_lost",
            evidence,
            prefix,
            [
                {
                    "method": "POST",
                    "path": "/api/method/frappe.client.submit",
                    "outcome": "upstream_completed_response_dropped",
                    "upstream_status": 200,
                }
            ],
        )
        self.assertTrue(result["passed"], result)


if __name__ == "__main__":
    unittest.main()
