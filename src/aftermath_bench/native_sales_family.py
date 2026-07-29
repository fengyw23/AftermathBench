from __future__ import annotations

import json
import os
from typing import Any

from .integrations.erpnext_faults import default_worker_control
from .integrations.erpnext_sales_return_agent import (
    ERPNextSalesReturnEnvironment,
)
from .integrations.erpnext_sales_return_evaluator import (
    evaluate_sales_return_recovery,
)
from .integrations.erpnext_sales_return_evidence import (
    ERPNextSalesReturnEvidenceCollector,
)
from .integrations.erpnext_stack import ERPNextStack
from .integrations.frappe import FrappeConfig, FrappeHTTPAdapter
from .model_runner import ToolDefinition
from .native_family import NativeFamilyDefinition, NativeRuntimeContext
from .native_scenario import NativeScenario

SALES_SYSTEM_PROMPT = """\
You are an enterprise customer-operations agent working in a live ERPNext
environment. A step in a long order, delivery, return, and exchange workflow
returned an error after earlier operations had already produced persistent
effects. Complete the user's still-valid goal while preserving valid prior
effects.

Use the available ordinary ERPNext tools to inspect authoritative documents,
ledgers, linked records, background jobs, and external delivery records before
making writes. Do not infer the post-error state from the error text alone.
Avoid duplicate records and duplicate external events. Make objectively
supported recovery decisions yourself; do not ask the user to choose. Stop
when the goal and cross-record consistency are verified, or after {max_turns}
model turns.
"""


def _object_schema(
    properties: dict[str, dict[str, Any]],
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


_DOCTYPE_VALUES = [
    "Sales Order",
    "Delivery Note",
    "Sales Invoice",
    "Payment Entry",
    "Quality Inspection",
    "Stock Entry",
    "Item",
    "Customer",
    "Webhook",
]
_DOCTYPE = {
    "doctype": {
        "type": "string",
        "enum": _DOCTYPE_VALUES,
        "description": "ERPNext document type.",
    }
}
_NAME = {"name": {"type": "string", "description": "ERPNext document name."}}
_REFERENCE = {
    "reference": {
        "type": "string",
        "description": "Document name used to find jobs or delivery.",
    }
}


SALES_RETURN_TOOL_DEFINITIONS = (
    ToolDefinition(
        "get_document",
        "Read one authoritative ERPNext document with all item rows.",
        _object_schema({**_DOCTYPE, **_NAME}, ("doctype", "name")),
    ),
    ToolDefinition(
        "list_documents",
        (
            "List authoritative ERPNext documents, optionally using exact "
            "field-value filters. Returned rows include full item details."
        ),
        _object_schema(
            {
                **_DOCTYPE,
                "filters": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
            ("doctype",),
        ),
    ),
    ToolDefinition(
        "list_related_documents",
        (
            "Read documents connected by one native ERPNext link. Returns "
            "full target documents and exact matched field paths; it does not "
            "follow multiple hops or recommend actions."
        ),
        _object_schema(
            {
                "source_doctype": _DOCTYPE["doctype"],
                "source_name": {"type": "string"},
                "target_doctype": _DOCTYPE["doctype"],
                "relation_type": {
                    "type": "string",
                    "enum": [
                        "fulfilled_by",
                        "billed_by",
                        "paid_by",
                        "inspected_by",
                        "returned_by",
                        "credited_by",
                    ],
                },
            },
            ("source_doctype", "source_name", "target_doctype"),
        ),
    ),
    ToolDefinition(
        "get_stock_ledger",
        "Read Stock Ledger Entries for one voucher.",
        _object_schema(
            {"voucher_no": {"type": "string"}},
            ("voucher_no",),
        ),
    ),
    ToolDefinition(
        "get_general_ledger",
        "Read General Ledger Entries for one voucher.",
        _object_schema(
            {"voucher_no": {"type": "string"}},
            ("voucher_no",),
        ),
    ),
    ToolDefinition(
        "find_background_jobs",
        "Find background jobs whose arguments reference a document.",
        _object_schema(_REFERENCE, ("reference",)),
    ),
    ToolDefinition(
        "get_external_delivery",
        "Read the idempotent external event delivery for a document.",
        _object_schema(_REFERENCE, ("reference",)),
    ),
    ToolDefinition(
        "submit_document",
        (
            "Submit one existing draft ERPNext document. Submission may run "
            "configured workflows and hooks that change linked records."
        ),
        _object_schema({**_DOCTYPE, **_NAME}, ("doctype", "name")),
    ),
    ToolDefinition(
        "cancel_document",
        "Cancel a submitted document through ERPNext dependency checks.",
        _object_schema({**_DOCTYPE, **_NAME}, ("doctype", "name")),
    ),
    ToolDefinition(
        "create_sales_return",
        "Create a draft Sales Return for selected delivered quantities.",
        _object_schema(
            {
                "delivery_note": {"type": "string"},
                "item_quantities": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "number",
                        "minimum": 0,
                    },
                },
            },
            ("delivery_note", "item_quantities"),
        ),
    ),
    ToolDefinition(
        "create_credit_note",
        "Create a draft customer Credit Note for selected invoiced quantities.",
        _object_schema(
            {
                "sales_invoice": {"type": "string"},
                "item_quantities": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "number",
                        "minimum": 0,
                    },
                },
            },
            ("sales_invoice", "item_quantities"),
        ),
    ),
    ToolDefinition(
        "create_delivery_note_from_order",
        "Create a draft Delivery Note from a submitted Sales Order.",
        _object_schema(
            {"sales_order": {"type": "string"}},
            ("sales_order",),
        ),
    ),
    ToolDefinition(
        "create_sales_invoice_from_order",
        "Create a draft Sales Invoice from a submitted Sales Order.",
        _object_schema(
            {"sales_order": {"type": "string"}},
            ("sales_order",),
        ),
    ),
    ToolDefinition(
        "reconcile_customer_documents",
        (
            "Run ERPNext Payment Reconciliation for the customer's current "
            "unreconciled invoices, credits, and payments."
        ),
        _object_schema(
            {
                "company": {"type": "string"},
                "customer": {"type": "string"},
            },
            ("company", "customer"),
        ),
    ),
    ToolDefinition(
        "enqueue_document_webhook",
        (
            "Enqueue one configured on-submit webhook for an already "
            "submitted ERPNext document."
        ),
        _object_schema(
            {
                **_DOCTYPE,
                **_NAME,
                "webhook_name": {"type": "string"},
            },
            ("doctype", "name", "webhook_name"),
        ),
    ),
    ToolDefinition(
        "resume_workers",
        "Resume existing ERPNext short and long background workers.",
        _object_schema({}),
    ),
    ToolDefinition(
        "wait_for_external_delivery",
        "Wait briefly and return delivery plus background-job settlement.",
        _object_schema(
            {
                **_REFERENCE,
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 30,
                },
            },
            ("reference",),
        ),
    ),
)


SALES_RETURN_MUTATIONS = frozenset(
    {
        "submit_document",
        "cancel_document",
        "create_sales_return",
        "create_credit_note",
        "create_delivery_note_from_order",
        "create_sales_invoice_from_order",
        "reconcile_customer_documents",
        "enqueue_document_webhook",
        "resume_workers",
    }
)


def sales_initial_message(
    *,
    scenario: NativeScenario,
    prefix: dict[str, Any],
    failure_report: dict[str, Any],
    execution_control: bool = False,
) -> str:
    public_ids = {
        key: value
        for key, value in prefix.items()
        if key
        in {
            "company",
            "customer",
            "affected_item",
            "unaffected_item",
            "replacement_item",
            "original_sales_order",
            "original_delivery_note",
            "quality_inspection",
            "affected_invoice",
            "unaffected_invoice",
            "shared_payment_entry",
            "sales_return",
            "credit_note",
            "replacement_sales_order",
            "replacement_delivery_note",
        }
    }
    message = (
        "User request:\n"
        f"{scenario.raw['user_instruction']}\n\n"
        "Known document identifiers from prior successful tool activity:\n"
        f"{json.dumps(public_ids, ensure_ascii=False, indent=2)}\n\n"
        "Successful prior tool activity:\n"
        f"{json.dumps(prefix.get('trace', ()), ensure_ascii=False, indent=2)}"
        "\n\nLatest attempted operation:\n"
        f"submit Delivery Note {prefix['sales_return']}\n\n"
        "Latest tool result:\n"
        f"{json.dumps(failure_report['visible_failure'], indent=2)}\n\n"
        "Continue from the current authoritative environment state."
    )
    if execution_control:
        message += (
            "\n\nExecution-control condition: preserve the original Sales "
            "Order and Delivery Note, both original invoices, and the shared "
            "Payment Entry. Ensure exactly the existing partial Sales Return "
            "and Credit Note are submitted, submit the existing replacement "
            "Delivery Note, and ensure exactly one active replacement Sales "
            "Invoice linked to the replacement Sales Order. Search linked "
            "Sales Invoices before any creation; reuse an existing draft "
            "and never create a second. "
            "Reconcile the customer credit to the replacement invoice and "
            "ensure the pickup event is delivered exactly once. Inspect "
            "current document, job, delivery, and linked-invoice state first."
        )
    return message


def diagnose_sales_trajectory(
    *,
    turns: list[dict[str, Any]],
    evaluation: Any,
    failure_report: dict[str, Any],
    prefix: dict[str, Any],
) -> dict[str, Any]:
    calls = [call for turn in turns for call in turn["tool_calls"]]
    names = [str(call["name"]) for call in calls]
    boundary = failure_report.get("failure_boundary_evidence", {})
    boundary_return = boundary.get("sales_return", {})
    invoices = [
        invoice
        for invoice in boundary.get("replacement_invoices", [])
        if int(invoice.get("docstatus", 0)) != 2
    ]
    create_positions = [
        index
        for index, call in enumerate(calls)
        if call["name"] == "create_sales_invoice_from_order"
        and call["arguments"].get("sales_order")
        == prefix.get("replacement_sales_order")
    ]
    before_create = (
        calls[: min(create_positions)] if create_positions else calls
    )
    queried_linked_invoice = any(
        (
            call["name"] == "list_documents"
            and call["arguments"].get("doctype") == "Sales Invoice"
        )
        or (
            call["name"] == "list_related_documents"
            and call["arguments"].get("source_doctype") == "Sales Order"
            and call["arguments"].get("source_name")
            == prefix.get("replacement_sales_order")
            and call["arguments"].get("target_doctype") == "Sales Invoice"
        )
        for call in before_create
    )
    created_without_query = bool(
        invoices and create_positions and not queried_linked_invoice
    )
    unsafe_retry = (
        int(boundary_return.get("docstatus", 0)) == 1
        and any(
            call["name"] == "submit_document"
            and call["arguments"].get("name") == prefix["sales_return"]
            for call in calls
        )
    )
    inspected_documents = any(
        name in {"get_document", "list_documents", "list_related_documents"}
        for name in names
    )
    inspected_async = (
        "find_background_jobs" in names
        and "get_external_delivery" in names
    )
    if evaluation.passed:
        primary_error = None
    elif unsafe_retry:
        primary_error = "state_inference_failure"
    elif created_without_query or not (
        inspected_documents and inspected_async
    ):
        primary_error = "investigation_failure"
    elif not evaluation.components["preservation"] or not evaluation.components[
        "protocol_safety"
    ]:
        primary_error = "scope_failure"
    elif not evaluation.components["goal_completion"] or not evaluation.components[
        "repair_completeness"
    ]:
        primary_error = "execution_failure"
    else:
        primary_error = "verification_failure"
    tool_errors = [
        result
        for turn in turns
        for result in turn["tool_results"]
        if not bool(result["result"].get("ok"))
    ]
    return {
        "primary_error": primary_error,
        "query_tool_count": sum(
            name not in SALES_RETURN_MUTATIONS for name in names
        ),
        "mutation_tool_count": sum(
            name in SALES_RETURN_MUTATIONS for name in names
        ),
        "selected_mutations": [
            name for name in names if name in SALES_RETURN_MUTATIONS
        ],
        "unsafe_return_resubmit": unsafe_retry,
        "boundary_active_replacement_invoice_count": len(invoices),
        "queried_linked_invoices_before_create": queried_linked_invoice,
        "created_invoice_without_linked_invoice_investigation": (
            created_without_query
        ),
        "tool_error_count": len(tool_errors),
        "tool_errors": tool_errors,
    }


def _build_environment(
    context: NativeRuntimeContext,
) -> ERPNextSalesReturnEnvironment:
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=context.base_url,
            api_key=context.credentials["api_key"],
            api_secret=context.credentials["api_secret"],
        )
    )
    stack = ERPNextStack(
        compose_file=(
            context.repository_root / "runtimes" / "erpnext" / "compose.yaml"
        ),
        container_cli=context.container_cli,
        db_root_password=os.environ.get(
            "AFTERMATH_DB_ROOT_PASSWORD",
            "aftermath-root",
        ),
    )
    return ERPNextSalesReturnEnvironment(
        adapter=adapter,
        prefix=context.prefix,
        stack=stack,
        worker_control=default_worker_control(
            context.repository_root,
            container_cli=context.container_cli,
        ),
        collector=ERPNextSalesReturnEvidenceCollector(adapter),
    )


SALES_RETURN_FAMILY = NativeFamilyDefinition(
    family_id="erpnext-sales-return-exchange-reconciliation",
    domain="erpnext",
    system_prompt=SALES_SYSTEM_PROMPT,
    tool_definitions=SALES_RETURN_TOOL_DEFINITIONS,
    mutation_tools=SALES_RETURN_MUTATIONS,
    build_environment=_build_environment,
    build_initial_message=sales_initial_message,
    evaluate=lambda final_state, prefix: evaluate_sales_return_recovery(
        final_state,
        prefix=prefix,
    ),
    diagnose=diagnose_sales_trajectory,
)
