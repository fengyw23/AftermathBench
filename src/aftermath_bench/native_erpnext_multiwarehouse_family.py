from __future__ import annotations

import json
import os
from typing import Any

from .integrations.erpnext_faults import default_worker_control
from .integrations.erpnext_multiwarehouse_agent import (
    ERPNextMultiwarehouseEnvironment,
)
from .integrations.erpnext_multiwarehouse_evaluator import (
    evaluate_multiwarehouse_recovery,
)
from .integrations.erpnext_multiwarehouse_evidence import (
    ERPNextMultiwarehouseEvidenceCollector,
)
from .integrations.erpnext_stack import ERPNextStack
from .integrations.frappe import FrappeConfig, FrappeHTTPAdapter
from .model_runner import ToolDefinition
from .native_family import NativeFamilyDefinition, NativeRuntimeContext
from .native_scenario import NativeScenario

MULTIWAREHOUSE_SYSTEM_PROMPT = """\
You are an inventory-operations agent working in a live ERPNext system. A
second-leg inter-warehouse Stock Entry returned a connection error after a
first transfer leg, material request, customer orders, reservations and stock
postings had already produced persistent effects. Complete the still-valid
transfer and reservation goal while preserving unrelated stock and prior work.

Inspect authoritative Stock Entries, material requests, warehouse balances,
stock ledgers, batch records, reservations, background jobs and arrival
deliveries before writing. Do not infer whether the failed submission committed
from the error text. Avoid duplicate incoming transfers, reservations,
reposting jobs and arrival deliveries. Make objectively supported recovery
decisions yourself and stop only after cross-record consistency is verified,
or after {max_turns} model turns.
"""


def _schema(
    properties: dict[str, dict[str, Any]], required: tuple[str, ...] = ()
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


_DOCTYPE_ENUM = [
    "Stock Entry",
    "Material Request",
    "Warehouse",
    "Item",
    "Batch",
    "Serial No",
    "Serial and Batch Bundle",
    "Sales Order",
    "Pick List",
    "Stock Reservation Entry",
    "Repost Item Valuation",
]
_DOCTYPE = {"doctype": {"type": "string", "enum": _DOCTYPE_ENUM}}
_NAME = {"name": {"type": "string"}}


ERP_NEXT_MULTIWAREHOUSE_TOOLS = (
    ToolDefinition(
        "get_document",
        "Read one authoritative ERPNext stock or reservation document.",
        _schema({**_DOCTYPE, **_NAME}, ("doctype", "name")),
    ),
    ToolDefinition(
        "list_documents",
        "List full ERPNext documents using optional exact field filters.",
        _schema(
            {**_DOCTYPE, "filters": {"type": "object", "additionalProperties": True}},
            ("doctype",),
        ),
    ),
    ToolDefinition(
        "list_related_documents",
        "Follow native ERPNext links between stock, order and reservation records.",
        _schema(
            {
                "source_doctype": {"type": "string", "enum": _DOCTYPE_ENUM},
                "source_name": {"type": "string"},
                "target_doctype": {"type": "string", "enum": _DOCTYPE_ENUM},
                "relation_type": {"type": "string"},
            },
            ("source_doctype", "source_name", "target_doctype"),
        ),
    ),
    ToolDefinition(
        "get_stock_ledger",
        "Read native Stock Ledger Entries for one voucher.",
        _schema({"voucher_no": {"type": "string"}}, ("voucher_no",)),
    ),
    ToolDefinition(
        "get_stock_balance",
        "Read authoritative Bin balances for one item and warehouse.",
        _schema(
            {
                "item_code": {"type": "string"},
                "warehouse": {"type": "string"},
            },
            ("item_code", "warehouse"),
        ),
    ),
    ToolDefinition(
        "find_background_jobs",
        "Find native background jobs whose arguments reference a document.",
        _schema({"reference": {"type": "string"}}, ("reference",)),
    ),
    ToolDefinition(
        "get_external_delivery",
        "Read the idempotent warehouse-arrival delivery for a Stock Entry.",
        _schema({"reference": {"type": "string"}}, ("reference",)),
    ),
    ToolDefinition(
        "submit_document",
        "Submit an existing draft through ERPNext validation and controllers.",
        _schema({**_DOCTYPE, **_NAME}, ("doctype", "name")),
    ),
    ToolDefinition(
        "cancel_document",
        "Cancel a submitted document through ERPNext dependency checks.",
        _schema({**_DOCTYPE, **_NAME}, ("doctype", "name")),
    ),
    ToolDefinition(
        "create_second_transfer_leg",
        "Map a submitted in-transit Stock Entry into a draft receiving leg.",
        _schema(
            {
                "outgoing_stock_entry": {"type": "string"},
                "destination_warehouse": {"type": "string"},
            },
            ("outgoing_stock_entry", "destination_warehouse"),
        ),
    ),
    ToolDefinition(
        "create_pick_list_from_sales_order",
        "Map one submitted Sales Order into a draft Pick List.",
        _schema({"sales_order": {"type": "string"}}, ("sales_order",)),
    ),
    ToolDefinition(
        "create_stock_reservation_entry",
        "Create one native stock reservation against an existing Sales Order item.",
        _schema(
            {
                "sales_order": {"type": "string"},
                "item_code": {"type": "string"},
                "warehouse": {"type": "string"},
                "quantity": {"type": "number", "exclusiveMinimum": 0},
            },
            ("sales_order", "item_code", "warehouse", "quantity"),
        ),
    ),
    ToolDefinition(
        "enqueue_document_webhook",
        "Enqueue one configured on-submit webhook for a submitted document.",
        _schema(
            {**_DOCTYPE, **_NAME, "webhook_name": {"type": "string"}},
            ("doctype", "name", "webhook_name"),
        ),
    ),
    ToolDefinition(
        "enqueue_stock_reposting",
        "Ask ERPNext's native scheduler to process queued stock valuation reposts.",
        _schema({}),
    ),
    ToolDefinition(
        "resume_workers",
        "Resume existing ERPNext short and long background workers.",
        _schema({}),
    ),
    ToolDefinition(
        "wait_for_external_delivery",
        "Wait briefly for warehouse-arrival delivery and queue settlement.",
        _schema(
            {
                "reference": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            ("reference",),
        ),
    ),
)


def multiwarehouse_initial_message(
    *,
    scenario: NativeScenario,
    prefix: dict[str, Any],
    failure_report: dict[str, Any],
    execution_control: bool = False,
) -> str:
    identifiers = {
        key: prefix[key]
        for key in (
            "company",
            "transfer_item",
            "transfer_quantity",
            "batch_id",
            "source_warehouse",
            "transit_warehouse",
            "destination_warehouse",
            "protected_warehouse",
            "material_request",
            "outgoing_stock_entry",
            "second_leg_stock_entry",
            "clinic_sales_order",
            "protected_sales_order",
            "protected_reservation",
            "arrival_webhook",
        )
    }
    message = (
        "User request:\n"
        f"{scenario.raw['user_instruction']}\n\n"
        "Known identifiers from prior successful activity:\n"
        f"{json.dumps(identifiers, ensure_ascii=False, indent=2)}\n\n"
        "Successful prior tool activity:\n"
        f"{json.dumps(prefix.get('trace', ()), ensure_ascii=False, indent=2)}\n\n"
        "Latest attempted tool call and result:\n"
        f"{json.dumps(failure_report['latest_attempt'], ensure_ascii=False, indent=2)}\n\n"
        "Continue from the current authoritative ERPNext and receiver state."
    )
    if execution_control:
        message += (
            "\n\nExecution-control condition: preserve the submitted first-leg "
            f"Stock Entry and the reservation in {prefix['protected_warehouse']}. "
            "Reuse the one "
            "prepared second leg; submit it only if draft. Ensure its arrival "
            "event is delivered exactly once, create and submit exactly one "
            f"Pick List and one {prefix['clinic_reserved_quantity']}-unit "
            "reservation against the clinic Sales Order, process any queued "
            "native reposting, and verify destination, transit and protected "
            "warehouse state."
        )
    return message


def diagnose_multiwarehouse_trajectory(
    *,
    turns: list[dict[str, Any]],
    evaluation: Any,
    failure_report: dict[str, Any],
    prefix: dict[str, Any],
) -> dict[str, Any]:
    del failure_report, prefix
    tools = [
        call.get("function", {}).get("name")
        for turn in turns
        for call in turn.get("assistant", {}).get("tool_calls", [])
    ]
    queried = set(tools)
    attribution: list[str] = []
    if not {
        "list_documents",
        "get_stock_ledger",
        "get_stock_balance",
        "get_external_delivery",
    }.issubset(queried):
        attribution.append("investigation_failure")
    if any(name in queried for name in ("cancel_document", "create_second_transfer_leg")):
        attribution.append("scope_failure")
    if evaluation.components.get("goal_completion") and not evaluation.components.get(
        "repair_completeness"
    ):
        attribution.append("execution_failure")
    if not evaluation.components.get("preservation"):
        attribution.append("scope_failure")
    if not attribution and not evaluation.passed:
        attribution.append("verification_failure")
    return {
        "primary": attribution[0] if attribution else "success",
        "all": sorted(set(attribution)),
        "tool_names": tools,
    }


def _build_environment(context: NativeRuntimeContext) -> ERPNextMultiwarehouseEnvironment:
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=context.base_url,
            api_key=context.credentials["api_key"],
            api_secret=context.credentials["api_secret"],
        )
    )
    stack = ERPNextStack(
        compose_file=context.repository_root / "runtimes" / "erpnext" / "compose.yaml",
        container_cli=context.container_cli,
        db_root_password=os.environ.get("AFTERMATH_DB_ROOT_PASSWORD", "aftermath-root"),
    )
    return ERPNextMultiwarehouseEnvironment(
        adapter=adapter,
        prefix=context.prefix,
        stack=stack,
        worker_control=default_worker_control(
            context.repository_root, container_cli=context.container_cli
        ),
        collector=ERPNextMultiwarehouseEvidenceCollector(adapter),
    )


ERP_NEXT_MULTIWAREHOUSE_FAMILY = NativeFamilyDefinition(
    family_id="erpnext-multiwarehouse-transfer",
    domain="erpnext",
    system_prompt=MULTIWAREHOUSE_SYSTEM_PROMPT,
    tool_definitions=ERP_NEXT_MULTIWAREHOUSE_TOOLS,
    mutation_tools=frozenset(ERPNextMultiwarehouseEnvironment.MUTATION_TOOLS),
    build_environment=_build_environment,
    build_initial_message=multiwarehouse_initial_message,
    evaluate=lambda final_state, prefix: evaluate_multiwarehouse_recovery(
        final_state, prefix=prefix
    ),
    diagnose=diagnose_multiwarehouse_trajectory,
)


__all__ = [
    "ERP_NEXT_MULTIWAREHOUSE_FAMILY",
    "ERP_NEXT_MULTIWAREHOUSE_TOOLS",
    "MULTIWAREHOUSE_SYSTEM_PROMPT",
    "multiwarehouse_initial_message",
]
