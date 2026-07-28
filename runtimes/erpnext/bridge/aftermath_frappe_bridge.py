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
