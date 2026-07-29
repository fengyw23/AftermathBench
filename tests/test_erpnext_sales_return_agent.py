from __future__ import annotations

import unittest

from aftermath_bench.integrations.erpnext_sales_return_agent import (
    reference_sales_return_recovery,
)


class _ReferenceFixture:
    def __init__(
        self,
        *,
        return_docstatus: int,
        delivered: bool,
        jobs: list[dict],
    ) -> None:
        self.prefix = {
            "sales_return": "DN-RETURN",
            "credit_note": "SINV-CREDIT",
            "replacement_delivery_note": "DN-EXCHANGE",
            "shared_payment_entry": "PAY-1",
            "quality_inspection": "QI-1",
            "company": "Aftermath Laboratories LLC",
            "customer": "Acme Field Services",
        }
        self.return_docstatus = return_docstatus
        self.credit_docstatus = 0
        self.replacement_delivery_docstatus = (
            1 if return_docstatus == 1 else 0
        )
        self.replacement_invoice = (
            {"name": "SINV-EXCHANGE", "docstatus": 0}
            if return_docstatus == 1
            else None
        )
        self.delivered = delivered
        self.jobs = jobs
        self.calls: list[tuple[str, dict]] = []

    def invoke(self, tool: str, **kwargs):
        self.calls.append((tool, kwargs))
        if tool == "get_document":
            name = kwargs["name"]
            if name == "DN-RETURN":
                document = {"name": name, "docstatus": self.return_docstatus}
            elif name == "SINV-CREDIT":
                document = {"name": name, "docstatus": self.credit_docstatus}
            elif name == "DN-EXCHANGE":
                document = {
                    "name": name,
                    "docstatus": self.replacement_delivery_docstatus,
                }
            else:
                document = {"name": name, "docstatus": 1}
            return {"ok": True, "document": document}
        if tool == "submit_document":
            name = kwargs["name"]
            if name == "DN-RETURN":
                self.return_docstatus = 1
                self.replacement_delivery_docstatus = 1
                self.replacement_invoice = {
                    "name": "SINV-EXCHANGE",
                    "docstatus": 0,
                }
                self.delivered = True
            elif name == "SINV-CREDIT":
                self.credit_docstatus = 1
            elif name == "SINV-EXCHANGE":
                assert self.replacement_invoice is not None
                self.replacement_invoice["docstatus"] = 1
            return {"ok": True, "document": {"name": name, "docstatus": 1}}
        if tool == "list_related_documents":
            related = (
                []
                if self.replacement_invoice is None
                else [{"document": dict(self.replacement_invoice)}]
            )
            return {"ok": True, "related": related}
        if tool == "create_sales_invoice_from_delivery":
            self.replacement_invoice = {
                "name": "SINV-EXCHANGE",
                "docstatus": 0,
            }
            return {"ok": True, "document": dict(self.replacement_invoice)}
        if tool == "get_external_delivery":
            return {"ok": True, "delivered": self.delivered}
        if tool == "find_background_jobs":
            return {"ok": True, "jobs": list(self.jobs)}
        if tool in {
            "reconcile_customer_documents",
            "enqueue_document_webhook",
            "resume_workers",
        }:
            return {"ok": True}
        if tool == "wait_for_external_delivery":
            self.delivered = True
            self.jobs = []
            return {"ok": True, "delivered": True, "jobs": []}
        if tool in {"get_stock_ledger", "get_general_ledger"}:
            return {"ok": True, "entries": []}
        raise AssertionError(tool)


class ERPNextSalesReturnReferenceTest(unittest.TestCase):
    @staticmethod
    def _mutations(fixture: _ReferenceFixture) -> list[str]:
        reference_sales_return_recovery(fixture)  # type: ignore[arg-type]
        query_tools = {
            "get_document",
            "list_related_documents",
            "get_external_delivery",
            "find_background_jobs",
            "wait_for_external_delivery",
            "get_stock_ledger",
            "get_general_ledger",
        }
        return [
            tool for tool, _arguments in fixture.calls if tool not in query_tools
        ]

    def test_request_not_reached_submits_return_without_duplicate_invoice(
        self,
    ) -> None:
        fixture = _ReferenceFixture(
            return_docstatus=0,
            delivered=False,
            jobs=[],
        )
        mutations = self._mutations(fixture)
        self.assertEqual(
            mutations,
            [
                "submit_document",
                "submit_document",
                "submit_document",
                "reconcile_customer_documents",
            ],
        )
        self.assertNotIn("create_sales_invoice_from_delivery", mutations)

    def test_committed_and_delivered_does_not_retry_return(self) -> None:
        fixture = _ReferenceFixture(
            return_docstatus=1,
            delivered=True,
            jobs=[],
        )
        self.assertEqual(
            self._mutations(fixture),
            [
                "submit_document",
                "submit_document",
                "reconcile_customer_documents",
            ],
        )

    def test_missing_pickup_job_is_enqueued(self) -> None:
        fixture = _ReferenceFixture(
            return_docstatus=1,
            delivered=False,
            jobs=[],
        )
        mutations = self._mutations(fixture)
        self.assertIn("enqueue_document_webhook", mutations)
        self.assertNotIn("resume_workers", mutations)

    def test_pending_pickup_job_resumes_workers(self) -> None:
        fixture = _ReferenceFixture(
            return_docstatus=1,
            delivered=False,
            jobs=[{"name": "job-1", "status": "queued"}],
        )
        mutations = self._mutations(fixture)
        self.assertIn("resume_workers", mutations)
        self.assertNotIn("enqueue_document_webhook", mutations)


if __name__ == "__main__":
    unittest.main()
