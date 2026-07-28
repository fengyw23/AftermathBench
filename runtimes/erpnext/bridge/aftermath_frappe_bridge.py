"""Auditable operational bridge into native Frappe recovery primitives.

This module is mounted read-only into the source-built ERPNext containers.  It
does not implement payment, accounting, queue, or webhook semantics.  It loads
authoritative Frappe documents and asks Frappe's own background-job subsystem
to run Frappe's own webhook delivery function.
"""

from __future__ import annotations

import frappe


def requeue_payment_remittance(
    payment_entry: str,
    webhook_name: str = "Aftermath Payment Remittance",
) -> dict[str, str]:
    payment = frappe.get_doc("Payment Entry", payment_entry)
    if payment.docstatus != 1:
        frappe.throw(
            f"Payment Entry {payment_entry} must be submitted before remittance"
        )

    webhook = frappe.get_doc("Webhook", webhook_name)
    if (
        not webhook.enabled
        or webhook.webhook_doctype != "Payment Entry"
        or webhook.webhook_docevent != "on_submit"
    ):
        frappe.throw(f"Webhook {webhook_name} is not an active payment-submit hook")

    job = frappe.enqueue(
        "frappe.integrations.doctype.webhook.webhook.enqueue_webhook",
        doc=payment,
        webhook=webhook,
        queue=webhook.background_jobs_queue or "default",
    )
    return {
        "job_id": str(job.id),
        "payment_entry": payment_entry,
        "webhook": webhook_name,
        "queue": webhook.background_jobs_queue or "default",
    }


def enqueue_document_webhook(
    doctype: str,
    document_name: str,
    webhook_name: str,
) -> dict[str, str]:
    """Enqueue one configured native webhook for a submitted document."""
    document = frappe.get_doc(doctype, document_name)
    if document.docstatus != 1:
        frappe.throw(
            f"{doctype} {document_name} must be submitted before enqueue"
        )
    webhook = frappe.get_doc("Webhook", webhook_name)
    if (
        not webhook.enabled
        or webhook.webhook_doctype != doctype
        or webhook.webhook_docevent != "on_submit"
    ):
        frappe.throw(
            f"Webhook {webhook_name} is not an active {doctype} submit hook"
        )
    job = frappe.enqueue(
        "frappe.integrations.doctype.webhook.webhook.enqueue_webhook",
        doc=document,
        webhook=webhook,
        queue=webhook.background_jobs_queue or "default",
    )
    return {
        "job_id": str(job.id),
        "doctype": doctype,
        "document_name": document_name,
        "webhook": webhook_name,
        "queue": webhook.background_jobs_queue or "default",
    }


def reconcile_supplier_documents(
    company: str,
    supplier: str,
) -> dict:
    """Run ERPNext's native Payment Reconciliation for one supplier."""
    from erpnext.accounts.party import get_party_account

    reconciliation = frappe.new_doc("Payment Reconciliation")
    reconciliation.company = company
    reconciliation.party_type = "Supplier"
    reconciliation.party = supplier
    reconciliation.receivable_payable_account = get_party_account(
        "Supplier",
        supplier,
        company,
    )
    reconciliation.get_unreconciled_entries()
    invoices = [
        row.as_dict() for row in reconciliation.get("invoices")
    ]
    payments = [
        row.as_dict() for row in reconciliation.get("payments")
    ]
    reconciliation.allocate_entries(
        frappe._dict({"invoices": invoices, "payments": payments})
    )
    allocations = [
        row.as_dict() for row in reconciliation.get("allocation")
    ]
    if not allocations:
        return {
            "company": company,
            "supplier": supplier,
            "allocation_count": 0,
            "reconciled": False,
        }
    reconciliation.reconcile()
    return {
        "company": company,
        "supplier": supplier,
        "allocation_count": len(allocations),
        "reconciled": True,
        "allocations": allocations,
    }
