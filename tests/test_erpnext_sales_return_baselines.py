from __future__ import annotations

import unittest
from typing import Any

from aftermath_bench.integrations.erpnext_sales_return_baselines import (
    run_fixed_sales_return_baseline,
)

PREFIX = {
    "sales_return": "DN-RETURN",
    "credit_note": "SINV-CREDIT",
    "replacement_delivery_note": "DN-EXCHANGE",
    "replacement_sales_order": "SO-EXCHANGE",
    "shared_payment_entry": "PAY-1",
    "unaffected_invoice": "SINV-U",
    "affected_invoice": "SINV-A",
    "original_delivery_note": "DN-ORIGINAL",
    "company": "Example LLC",
    "customer": "Example Customer",
}


class FakeEnvironment:
    def __init__(self, *, return_docstatus: int, retry_ok: bool = True):
        self.return_docstatus = return_docstatus
        self.retry_ok = retry_ok
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def invoke(self, tool: str, **arguments: Any) -> dict[str, Any]:
        self.calls.append((tool, arguments))
        if (
            tool == "submit_document"
            and arguments.get("name") == PREFIX["sales_return"]
        ):
            return {"ok": self.retry_ok}
        if tool == "get_document":
            return {
                "ok": True,
                "document": {"docstatus": self.return_docstatus},
            }
        if tool == "get_external_delivery":
            return {"ok": True, "delivered": True}
        if tool == "find_background_jobs":
            return {"ok": True, "jobs": []}
        if tool == "create_sales_invoice_from_order":
            return {
                "ok": True,
                "document": {"name": "SINV-EXCHANGE"},
            }
        return {"ok": True}


class SalesReturnBaselineTest(unittest.TestCase):
    def test_blind_retry_stops_after_rejected_retry(self) -> None:
        environment = FakeEnvironment(return_docstatus=1, retry_ok=False)
        trace = run_fixed_sales_return_baseline(
            "blind_retry",
            environment=environment,  # type: ignore[arg-type]
            prefix=PREFIX,
        )
        self.assertEqual([step["tool"] for step in trace], ["submit_document"])

    def test_assume_committed_never_reads_boundary_state(self) -> None:
        environment = FakeEnvironment(return_docstatus=1)
        trace = run_fixed_sales_return_baseline(
            "assume_committed",
            environment=environment,  # type: ignore[arg-type]
            prefix=PREFIX,
        )
        names = [step["tool"] for step in trace]
        self.assertNotIn("get_document", names)
        self.assertIn("create_sales_invoice_from_order", names)

    def test_compact_tree_queries_boundary_then_runs_fixed_sequence(
        self,
    ) -> None:
        environment = FakeEnvironment(return_docstatus=1)
        trace = run_fixed_sales_return_baseline(
            "compact_boundary_tree",
            environment=environment,  # type: ignore[arg-type]
            prefix=PREFIX,
        )
        names = [step["tool"] for step in trace]
        self.assertEqual(
            names[:3],
            [
                "get_document",
                "get_external_delivery",
                "find_background_jobs",
            ],
        )
        self.assertIn("create_sales_invoice_from_order", names)


if __name__ == "__main__":
    unittest.main()
