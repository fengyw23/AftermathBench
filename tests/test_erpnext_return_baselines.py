from __future__ import annotations

from typing import Any

from aftermath_bench.integrations.erpnext_return_baselines import (
    run_fixed_return_baseline,
)


PREFIX = {
    "purchase_return": "PREC-RET-001",
    "debit_note": "PINV-DN-001",
    "replacement_purchase_receipt": "PREC-REP-001",
    "shared_payment_entry": "PAY-001",
    "unaffected_invoice": "PINV-U-001",
    "affected_invoice": "PINV-A-001",
    "original_purchase_receipt": "PREC-001",
    "company": "Example LLC",
    "supplier": "Example Supplier",
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
            and arguments.get("name") == PREFIX["purchase_return"]
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
        if tool == "create_purchase_invoice_from_receipt":
            return {
                "ok": True,
                "document": {"name": "PINV-REP-001"},
            }
        return {"ok": True}


def test_blind_retry_aborts_after_a_committed_return_rejects_retry():
    environment = FakeEnvironment(return_docstatus=1, retry_ok=False)
    trace = run_fixed_return_baseline(
        "blind_retry",
        environment=environment,  # type: ignore[arg-type]
        prefix=PREFIX,
    )
    assert [step["tool"] for step in trace] == ["submit_document"]


def test_blind_retry_only_completes_downstream_after_retry_succeeds():
    environment = FakeEnvironment(return_docstatus=0, retry_ok=True)
    trace = run_fixed_return_baseline(
        "blind_retry",
        environment=environment,  # type: ignore[arg-type]
        prefix=PREFIX,
    )
    names = [step["tool"] for step in trace]
    assert names[0] == "submit_document"
    assert "create_purchase_invoice_from_receipt" in names
    assert "reconcile_supplier_documents" in names


def test_compact_tree_uses_boundary_tree_then_fixed_downstream_sequence():
    environment = FakeEnvironment(return_docstatus=1)
    trace = run_fixed_return_baseline(
        "compact_boundary_tree",
        environment=environment,  # type: ignore[arg-type]
        prefix=PREFIX,
    )
    names = [step["tool"] for step in trace]
    assert names[:3] == [
        "get_document",
        "get_external_delivery",
        "find_background_jobs",
    ]
    assert "create_purchase_invoice_from_receipt" in names
    assert "reconcile_supplier_documents" in names
