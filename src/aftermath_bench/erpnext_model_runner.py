from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .core import canonical_fingerprint
from .integrations.erpnext_agent import ERPNextRecoveryEnvironment
from .integrations.erpnext_evaluator import evaluate_erpnext_recovery
from .integrations.erpnext_evidence import (
    ERPNextEvidenceCollector,
    ProcurementPaymentIDs,
)
from .integrations.erpnext_faults import default_worker_control
from .integrations.erpnext_stack import ERPNextStack
from .integrations.frappe import FrappeConfig, FrappeHTTPAdapter
from .model_runner import (
    ChatClient,
    ToolCall,
    ToolDefinition,
    _assistant_message,
    _without_private_reasoning,
)
from .schema import repository_root


ERP_NEXT_SYSTEM_PROMPT = """\
You are an enterprise procurement recovery agent operating a live ERPNext
environment. A previous tool call failed ambiguously after an otherwise
successful procurement workflow.

Complete the user's still-valid payment and supplier-remittance goal while
preserving valid purchase, receipt, invoice, stock, and accounting effects.
Inspect authoritative current records before making recovery writes. A timeout
does not prove that the attempted operation failed. Avoid duplicate payments,
duplicate remittance jobs, and duplicate remittance deliveries. Use only the
provided tools, make recovery decisions yourself when the records are
sufficient, and do not ask the user to choose among objectively verifiable
repairs. Stop calling tools once the goal is verified or after {max_turns}
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


_PURCHASE_ORDER = {
    "purchase_order": {
        "type": "string",
        "description": "ERPNext Purchase Order document name.",
    }
}
_PURCHASE_RECEIPT = {
    "purchase_receipt": {
        "type": "string",
        "description": "ERPNext Purchase Receipt document name.",
    }
}
_PURCHASE_INVOICE = {
    "purchase_invoice": {
        "type": "string",
        "description": "ERPNext Purchase Invoice document name.",
    }
}
_PAYMENT_ENTRY = {
    "payment_entry": {
        "type": "string",
        "description": "ERPNext Payment Entry document name.",
    }
}


ERP_NEXT_TOOL_DEFINITIONS = (
    ToolDefinition(
        "get_purchase_order",
        "Read the authoritative Purchase Order and its current document state.",
        _object_schema(_PURCHASE_ORDER, ("purchase_order",)),
    ),
    ToolDefinition(
        "get_purchase_receipt",
        "Read the authoritative Purchase Receipt and received item quantities.",
        _object_schema(_PURCHASE_RECEIPT, ("purchase_receipt",)),
    ),
    ToolDefinition(
        "get_purchase_invoice",
        (
            "Read the authoritative Purchase Invoice, including document "
            "status, total, and outstanding amount."
        ),
        _object_schema(_PURCHASE_INVOICE, ("purchase_invoice",)),
    ),
    ToolDefinition(
        "get_payment_entry",
        (
            "Read a Payment Entry, including submission status, paid amount, "
            "and invoice references."
        ),
        _object_schema(_PAYMENT_ENTRY, ("payment_entry",)),
    ),
    ToolDefinition(
        "find_payments_for_invoice",
        (
            "Find every Payment Entry that currently references a Purchase "
            "Invoice. Use this to detect existing or duplicate payments."
        ),
        _object_schema(_PURCHASE_INVOICE, ("purchase_invoice",)),
    ),
    ToolDefinition(
        "get_payment_ledger",
        "Read General Ledger entries created by a Payment Entry.",
        _object_schema(_PAYMENT_ENTRY, ("payment_entry",)),
    ),
    ToolDefinition(
        "find_remittance_jobs",
        (
            "Find background RQ jobs associated with the supplier remittance "
            "for a Payment Entry."
        ),
        _object_schema(_PAYMENT_ENTRY, ("payment_entry",)),
    ),
    ToolDefinition(
        "get_remittance_delivery",
        (
            "Read the idempotent remittance receiver's delivery record and "
            "attempt count for a Payment Entry."
        ),
        _object_schema(_PAYMENT_ENTRY, ("payment_entry",)),
    ),
    ToolDefinition(
        "submit_payment_entry",
        (
            "Submit an existing draft Payment Entry through ERPNext. Do not "
            "call this unless current records show that submission is needed."
        ),
        _object_schema(_PAYMENT_ENTRY, ("payment_entry",)),
    ),
    ToolDefinition(
        "requeue_payment_remittance",
        (
            "Create the native remittance webhook job for an already submitted "
            "Payment Entry when no delivery or existing job can complete it."
        ),
        _object_schema(_PAYMENT_ENTRY, ("payment_entry",)),
    ),
    ToolDefinition(
        "resume_remittance_workers",
        (
            "Resume the existing short and long queue workers so already "
            "queued remittance work can continue."
        ),
        _object_schema({}),
    ),
    ToolDefinition(
        "wait_for_remittance_delivery",
        (
            "Wait briefly, then report both remittance delivery and relevant "
            "job settlement."
        ),
        _object_schema(
            {
                **_PAYMENT_ENTRY,
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 30,
                    "description": "How long to wait before returning evidence.",
                },
            },
            ("payment_entry",),
        ),
    ),
)


ERP_NEXT_MUTATION_TOOLS = {
    "submit_payment_entry",
    "requeue_payment_remittance",
    "resume_remittance_workers",
}


def erpnext_initial_message(
    *,
    prefix: dict[str, Any],
    failure_report: dict[str, Any],
) -> str:
    visible_failure = failure_report.get(
        "visible_failure",
        {
            "ok": False,
            "error": "connection_lost_before_confirmation",
        },
    )
    return (
        "User request:\n"
        f"Complete payment of Purchase Invoice {prefix['purchase_invoice']} "
        f"using the existing Payment Entry {prefix['payment_entry']}, ensure "
        "the supplier remittance is delivered exactly once, and preserve the "
        "already completed procurement records.\n\n"
        "Successful prior tool activities:\n"
        f"{json.dumps(prefix.get('trace', ()), ensure_ascii=False, indent=2)}"
        "\n\nLatest attempted operation:\n"
        f"submit Payment Entry {prefix['payment_entry']}\n\n"
        "Latest tool result:\n"
        f"{json.dumps(visible_failure, ensure_ascii=False, indent=2)}\n\n"
        "Continue from the current authoritative environment state."
    )


def _invoke_model_tool(
    environment: ERPNextRecoveryEnvironment,
    allowed_tools: set[str],
    call: ToolCall,
) -> dict[str, Any]:
    if call.name not in allowed_tools:
        return {"ok": False, "error": f"unknown or unavailable tool: {call.name}"}
    if "__argument_parse_error__" in call.arguments:
        return {"ok": False, "error": "tool arguments were not valid JSON"}
    try:
        return environment.invoke(call.name, **call.arguments)
    except TypeError as error:
        return {"ok": False, "error": f"invalid tool arguments: {error}"}
    except (KeyError, ValueError) as error:
        return {"ok": False, "error": str(error)}


def _trajectory_diagnostics(
    *,
    turns: list[dict[str, Any]],
    failure_report: dict[str, Any],
) -> dict[str, Any]:
    calls = [call for turn in turns for call in turn["tool_calls"]]
    tool_names = [call["name"] for call in calls]
    query_tools = [
        name for name in tool_names if name not in ERP_NEXT_MUTATION_TOOLS
    ]
    mutation_tools = [
        name for name in tool_names if name in ERP_NEXT_MUTATION_TOOLS
    ]
    tool_errors = [
        result
        for turn in turns
        for result in turn["tool_results"]
        if not bool(result["result"].get("ok"))
    ]
    boundary = failure_report.get("failure_boundary_evidence", {})
    submitted_at_boundary = any(
        int(payment.get("docstatus", 0)) == 1
        for payment in boundary.get("payment_entries", ())
    )
    delivery_at_boundary = boundary.get("remittance") is not None
    return {
        "tool_call_count": len(calls),
        "query_tool_count": len(query_tools),
        "mutation_tool_count": len(mutation_tools),
        "unique_query_tools": sorted(set(query_tools)),
        "selected_mutations": mutation_tools,
        "tool_error_count": len(tool_errors),
        "tool_errors": tool_errors,
        "inspected_payment_state": (
            "get_payment_entry" in tool_names
            or "find_payments_for_invoice" in tool_names
        ),
        "inspected_remittance_state": (
            "get_remittance_delivery" in tool_names
            and "find_remittance_jobs" in tool_names
        ),
        "unsafe_submit_retry": (
            submitted_at_boundary
            and "submit_payment_entry" in mutation_tools
        ),
        "unnecessary_remittance_requeue": (
            delivery_at_boundary
            and "requeue_payment_remittance" in mutation_tools
        ),
    }


def run_erpnext_agent(
    client: ChatClient,
    *,
    environment: ERPNextRecoveryEnvironment,
    variant: str,
    prefix: dict[str, Any],
    failure_report: dict[str, Any],
    max_turns: int = 15,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    if max_turns < 1:
        raise ValueError("max_turns must be positive")
    system = ERP_NEXT_SYSTEM_PROMPT.format(max_turns=max_turns)
    initial_message = erpnext_initial_message(
        prefix=prefix,
        failure_report=failure_report,
    )
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": initial_message}
    ]
    model_turns: list[dict[str, Any]] = []
    stop_reason = "turn_limit"
    allowed_tools = {tool.name for tool in ERP_NEXT_TOOL_DEFINITIONS}

    for turn_index in range(1, max_turns + 1):
        turn = client.complete(
            system=system,
            messages=messages,
            tools=ERP_NEXT_TOOL_DEFINITIONS,
        )
        messages.append(_assistant_message(turn))
        turn_record: dict[str, Any] = {
            "turn": turn_index,
            "text": turn.text,
            "tool_calls": [asdict(call) for call in turn.tool_calls],
            "usage": turn.usage,
            "provider_stop_reason": turn.stop_reason,
            "raw_response": _without_private_reasoning(turn.raw_response),
            "tool_results": [],
        }
        model_turns.append(turn_record)
        if not turn.tool_calls:
            stop_reason = "model_stopped"
            break
        for call in turn.tool_calls:
            result = _invoke_model_tool(environment, allowed_tools, call)
            turn_record["tool_results"].append(
                {
                    "call_id": call.call_id,
                    "name": call.name,
                    "result": result,
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.call_id,
                    "name": call.name,
                    "content": json.dumps(
                        result,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )

    final_state = environment.snapshot()
    evaluation = evaluate_erpnext_recovery(
        final_state,
        expected_prefix_fingerprints=prefix["protected_fingerprints"],
    )
    report = {
        "schema_version": "0.4",
        "run_id": (
            f"erpnext-procurement-payment-001--{variant}--"
            f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        ),
        "task_id": "erpnext-procurement-payment-001",
        "variant": variant,
        "provider": client.provider,
        "model": client.model,
        "max_turns": max_turns,
        "stop_reason": stop_reason,
        "surface_failure": failure_report.get("visible_failure"),
        "system_prompt": system,
        "initial_message": initial_message,
        "turns": model_turns,
        "environment_tool_events": environment.event_log(),
        "final_state_sha256": canonical_fingerprint(final_state),
        "final_evidence": final_state,
        "evaluation": {
            "passed": evaluation.passed,
            "checks": evaluation.checks,
            "diagnostics": evaluation.diagnostics,
            "failures": evaluation.failures,
        },
        "trajectory_diagnostics": _trajectory_diagnostics(
            turns=model_turns,
            failure_report=failure_report,
        ),
    }
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report


def run_live_erpnext_agent(
    client: ChatClient,
    *,
    variant: str,
    credentials_path: str | Path,
    prefix_path: str | Path,
    failure_report_path: str | Path,
    max_turns: int = 15,
    output_path: str | Path | None = None,
    erpnext_base_url: str = "http://127.0.0.1:8080",
    container_cli: str = "docker",
) -> dict[str, Any]:
    root = repository_root()
    runtime = root / "runtimes" / "erpnext"
    credentials = json.loads(
        Path(credentials_path).read_text(encoding="utf-8")
    )
    prefix = json.loads(Path(prefix_path).read_text(encoding="utf-8"))
    failure_report = json.loads(
        Path(failure_report_path).read_text(encoding="utf-8")
    )
    if failure_report.get("variant") != variant:
        raise ValueError(
            "failure report variant does not match requested model run"
        )
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=erpnext_base_url,
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
        )
    )
    ids = ProcurementPaymentIDs(
        purchase_order=prefix["purchase_order"],
        purchase_receipt=prefix["purchase_receipt"],
        purchase_invoice=prefix["purchase_invoice"],
    )
    stack = ERPNextStack(
        compose_file=runtime / "compose.yaml",
        container_cli=container_cli,
        db_root_password=os.environ.get(
            "AFTERMATH_DB_ROOT_PASSWORD",
            "aftermath-root",
        ),
    )
    environment = ERPNextRecoveryEnvironment(
        adapter=adapter,
        ids=ids,
        payment_entry=prefix["payment_entry"],
        stack=stack,
        worker_control=default_worker_control(
            root,
            container_cli=container_cli,
        ),
        collector=ERPNextEvidenceCollector(adapter),
    )
    return run_erpnext_agent(
        client,
        environment=environment,
        variant=variant,
        prefix=prefix,
        failure_report=failure_report,
        max_turns=max_turns,
        output_path=output_path,
    )
