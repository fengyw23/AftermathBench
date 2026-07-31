from __future__ import annotations

import unittest
from unittest.mock import patch

from aftermath_bench.integrations.erpnext_sales_return_evidence import (
    ERPNextSalesReturnEvidenceCollector,
)


class _Adapter:
    def get_resource(self, doctype, name):
        return {
            "data": {
                "doctype": doctype,
                "name": name,
                "docstatus": 0,
                "items": [],
            }
        }

    def list_resources(self, doctype, **kwargs):
        if doctype == "RQ Job":
            return {
                "data": [
                    {
                        "name": "job-unrelated",
                        "job_name": "background_cleanup",
                        "status": "finished",
                        "arguments": "{}",
                        "queue": "short",
                    },
                    {
                        "name": "job-target",
                        "job_name": "enqueue_webhook",
                        "status": "queued",
                        "arguments": '{"doc":{"name":"DN-RETURN-1"}}',
                        "queue": "short",
                    },
                ]
            }
        return {"data": []}


class ERPNextSalesReturnEvidenceCollectorTest(unittest.TestCase):
    @patch.object(
        ERPNextSalesReturnEvidenceCollector,
        "get_delivery",
        return_value=None,
    )
    def test_filters_queue_evidence_to_the_target_return(self, _delivery):
        prefix = {
            "stock_seed": "STE-1",
            "original_sales_order": "SO-1",
            "original_delivery_note": "DN-1",
            "quality_inspection": "QI-1",
            "affected_invoice": "SI-1",
            "unaffected_invoice": "SI-2",
            "shared_payment_entry": "PAY-1",
            "sales_return": "DN-RETURN-1",
            "credit_note": "CN-1",
            "replacement_sales_order": "SO-2",
            "replacement_delivery_note": "DN-2",
        }
        evidence = ERPNextSalesReturnEvidenceCollector(_Adapter()).collect(
            prefix
        )
        self.assertEqual(
            [job["name"] for job in evidence["rq_jobs"]],
            ["job-target"],
        )


if __name__ == "__main__":
    unittest.main()
