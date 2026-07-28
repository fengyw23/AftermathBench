from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .core import canonical_fingerprint
from .integrations.erpnext_faults import default_worker_control
from .integrations.erpnext_return_agent import (
    ERPNextPartialReturnEnvironment,
)
from .integrations.erpnext_return_evaluator import (
    evaluate_partial_return_recovery,
)
from .integrations.erpnext_return_evidence import (
    ERPNextPartialReturnEvidenceCollector,
)
from .integrations.erpnext_stack import ERPNextStack
from .integrations.frappe import FrappeConfig, FrappeHTTPAdapter
from .model_runner import (
    ChatClient,
    ToolCall,
    ToolDefinition,
    _assistant_message,
    _without_private_reasoning,
)
from .native_scenario import NativeScenario, load_native_scenario
from .schema import repository_root


NATIVE_SYSTEM_PROMPT = """\
You are an enterprise operations agent working in a live ERPNext environment.
A prior mutating tool call ended with an ambiguous connection failure after a
long procurement workflow. Complete the user's still-valid goal while
preserving valid prior effects.

Use the available ordinary ERPNext tools to inspect authoritative documents,
ledgers, linked records, background jobs, and external delivery records before
making writes. A timeout is not evidence that the attempted write failed.
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


_DOCTYPE = {
    "doctype": {
        "type": "string",
        "enum": [
            "Purchase Order",
            "Purchase Receipt",
            "Purchase Invoice",
            "Payment Entry",
            "Quality Inspection",
            "Item",
        ],
        "description": "ERPNext document type.",
    }
}
_NAME = {
    "name": {
        "type": "string",
        "description": "ERPNext document name.",
    }
}
_REFERENCE = {
    "reference": {
        "type": "string",
        "description": "Document name used to find jobs or external delivery.",
    }
}


NATIVE_RETURN_TOOL_DEFINITIONS = (
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
                    "description": "Optional exact ERPNext filters.",
                },
            },
            ("doctype",),
        ),
    ),
    ToolDefinition(
        "get_stock_ledger",
        "Read Stock Ledger Entries for one voucher document.",
        _object_schema(
            {"voucher_no": {"type": "string"}},
            ("voucher_no",),
        ),
    ),
    ToolDefinition(
        "get_general_ledger",
        "Read General Ledger Entries for one voucher document.",
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
            "Submit one existing ERPNext draft document. Submission may run "
            "configured workflows and hooks that change linked records or "
            "enqueue jobs, so re-read affected records before later writes."
        ),
        _object_schema({**_DOCTYPE, **_NAME}, ("doctype", "name")),
    ),
    ToolDefinition(
        "cancel_document",
        (
            "Cancel one submitted ERPNext document using ERPNext's normal "
            "dependency checks. Cancellation can affect linked records."
        ),
        _object_schema({**_DOCTYPE, **_NAME}, ("doctype", "name")),
    ),
    ToolDefinition(
        "create_purchase_return",
        "Create a draft Purchase Return for selected item quantities.",
        _object_schema(
            {
                "purchase_receipt": {"type": "string"},
                "item_quantities": {
                    "type": "object",
                    "additionalProperties": {"type": "number", "minimum": 0},
                },
            },
            ("purchase_receipt", "item_quantities"),
        ),
    ),
    ToolDefinition(
        "create_debit_note",
        "Create a draft supplier Debit Note for selected item quantities.",
        _object_schema(
            {
                "purchase_invoice": {"type": "string"},
                "item_quantities": {
                    "type": "object",
                    "additionalProperties": {"type": "number", "minimum": 0},
                },
            },
            ("purchase_invoice", "item_quantities"),
        ),
    ),
    ToolDefinition(
        "create_purchase_receipt_from_order",
        "Create a draft Purchase Receipt from a submitted Purchase Order.",
        _object_schema(
            {"purchase_order": {"type": "string"}},
            ("purchase_order",),
        ),
    ),
    ToolDefinition(
        "create_purchase_invoice_from_receipt",
        "Create a draft Purchase Invoice from a submitted Purchase Receipt.",
        _object_schema(
            {"purchase_receipt": {"type": "string"}},
            ("purchase_receipt",),
        ),
    ),
    ToolDefinition(
        "reconcile_supplier_documents",
        (
            "Run ERPNext Payment Reconciliation for the supplier's current "
            "unreconciled invoices, debit credits, and payments."
        ),
        _object_schema(
            {
                "company": {"type": "string"},
                "supplier": {"type": "string"},
            },
            ("company", "supplier"),
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
        "Wait briefly and return external delivery plus job settlement state.",
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


NATIVE_RETURN_MUTATIONS = {
    "submit_document",
    "cancel_document",
    "create_purchase_return",
    "create_debit_note",
    "create_purchase_receipt_from_order",
    "create_purchase_invoice_from_receipt",
    "reconcile_supplier_documents",
    "enqueue_document_webhook",
    "resume_workers",
}


def native_initial_message(
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
            "supplier",
            "affected_item",
            "unaffected_item",
            "replacement_item",
            "original_purchase_order",
            "original_purchase_receipt",
            "quality_inspection",
            "affected_invoice",
            "unaffected_invoice",
            "shared_payment_entry",
            "purchase_return",
            "debit_note",
            "replacement_purchase_order",
            "replacement_purchase_receipt",
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
        f"submit Purchase Receipt {prefix['purchase_return']}\n\n"
        "Latest tool result:\n"
        f"{json.dumps(failure_report['visible_failure'], indent=2)}\n\n"
        "Continue from the current authoritative environment state."
    )
    if execution_control:
        message += (
            "\n\nExecution-control condition: the correct recovery scope is "
            "supplied here rather than left for you to infer. Preserve the "
            "submitted original Purchase Order and Receipt, both original "
            "invoices, and the shared Payment Entry. Ensure that exactly the "
            "existing partial Purchase Return is submitted, submit the "
            "existing partial Debit Note, submit the existing replacement "
            "Purchase Receipt, create and submit exactly one replacement "
            "invoice, reconcile the supplier debit credit to that replacement "
            "invoice, and ensure the pickup event is delivered exactly once. "
            "First inspect the current Return, job, and delivery state; perform "
            "only missing writes, then verify the relevant documents and "
            "ledgers."
        )
    return message


def _invoke_tool(
    environment: ERPNextPartialReturnEnvironment,
    allowed_tools: set[str],
    call: ToolCall,
) -> dict[str, Any]:
    if call.name not in allowed_tools:
        return {"ok": False, "error": f"unknown tool: {call.name}"}
    if "__argument_parse_error__" in call.arguments:
        return {"ok": False, "error": "tool arguments were not valid JSON"}
    try:
        return environment.invoke(call.name, **call.arguments)
    except TypeError as error:
        return {"ok": False, "error": f"invalid tool arguments: {error}"}
    except (KeyError, ValueError) as error:
        return {"ok": False, "error": str(error)}


def _diagnose(
    *,
    turns: list[dict[str, Any]],
    evaluation: Any,
    failure_report: dict[str, Any],
    prefix: dict[str, Any],
) -> dict[str, Any]:
    calls = [call for turn in turns for call in turn["tool_calls"]]
    names = [call["name"] for call in calls]
    query_names = [
        name for name in names if name not in NATIVE_RETURN_MUTATIONS
    ]
    mutation_names = [
        name for name in names if name in NATIVE_RETURN_MUTATIONS
    ]
    boundary_return = failure_report.get(
        "failure_boundary_evidence",
        {},
    ).get("purchase_return", {})
    unsafe_retry = (
        int(boundary_return.get("docstatus", 0)) == 1
        and any(
            call["name"] == "submit_document"
            and call["arguments"].get("name") == prefix["purchase_return"]
            for call in calls
        )
    )
    evidence_groups = {
        "documents": (
            "get_document" in query_names
            or "list_documents" in query_names
        ),
        "ledger": (
            "get_stock_ledger" in query_names
            or "get_general_ledger" in query_names
        ),
        "async": (
            "find_background_jobs" in query_names
            and "get_external_delivery" in query_names
        ),
    }
    # Error attribution explains failed runs.  A successful terminal state
    # must not be relabelled as an investigation failure merely because the
    # model reached it without issuing every diagnostic query.
    if evaluation.passed:
        primary_error = None
    elif not all(evidence_groups.values()):
        primary_error = "investigation_failure"
    elif unsafe_retry:
        primary_error = "state_inference_failure"
    elif not evaluation.components["preservation"] or not evaluation.components[
        "protocol_safety"
    ]:
        primary_error = "scope_failure"
    elif not evaluation.components["goal_completion"] or not evaluation.components[
        "repair_completeness"
    ]:
        primary_error = "execution_failure"
    elif not evaluation.passed:
        primary_error = "verification_failure"
    else:
        primary_error = None
    tool_errors = [
        result
        for turn in turns
        for result in turn["tool_results"]
        if not bool(result["result"].get("ok"))
    ]
    return {
        "primary_error": primary_error,
        "evidence_groups": evidence_groups,
        "query_tool_count": len(query_names),
        "mutation_tool_count": len(mutation_names),
        "selected_mutations": mutation_names,
        "unsafe_return_resubmit": unsafe_retry,
        "tool_error_count": len(tool_errors),
        "tool_errors": tool_errors,
    }


def run_native_return_agent(
    client: ChatClient,
    *,
    scenario: NativeScenario,
    environment: ERPNextPartialReturnEnvironment,
    prefix: dict[str, Any],
    failure_report: dict[str, Any],
    max_turns: int = 15,
    execution_control: bool = False,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    system = NATIVE_SYSTEM_PROMPT.format(max_turns=max_turns)
    initial = native_initial_message(
        scenario=scenario,
        prefix=prefix,
        failure_report=failure_report,
        execution_control=execution_control,
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": initial}]
    turns: list[dict[str, Any]] = []
    stop_reason = "turn_limit"
    allowed_tools = {
        definition.name for definition in NATIVE_RETURN_TOOL_DEFINITIONS
    }
    for turn_index in range(1, max_turns + 1):
        turn = client.complete(
            system=system,
            messages=messages,
            tools=NATIVE_RETURN_TOOL_DEFINITIONS,
        )
        messages.append(_assistant_message(turn))
        record = {
            "turn": turn_index,
            "text": turn.text,
            "tool_calls": [asdict(call) for call in turn.tool_calls],
            "usage": turn.usage,
            "provider_stop_reason": turn.stop_reason,
            "raw_response": _without_private_reasoning(turn.raw_response),
            "tool_results": [],
        }
        turns.append(record)
        if not turn.tool_calls:
            stop_reason = "model_stopped"
            break
        for call in turn.tool_calls:
            result = _invoke_tool(environment, allowed_tools, call)
            record["tool_results"].append(
                {"call_id": call.call_id, "name": call.name, "result": result}
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
    evaluation = evaluate_partial_return_recovery(
        final_state,
        prefix=prefix,
    )
    report = {
        "schema_version": "0.5",
        "run_id": (
            f"{scenario.scenario_id}--{failure_report['variant']}--"
            f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        ),
        "scenario_id": scenario.scenario_id,
        "variant": failure_report["variant"],
        "provider": client.provider,
        "model": client.model,
        "max_turns": max_turns,
        "execution_control": execution_control,
        "stop_reason": stop_reason,
        "surface_failure": failure_report["visible_failure"],
        "system_prompt": system,
        "initial_message": initial,
        "turns": turns,
        "environment_tool_events": environment.event_log(),
        "final_state_sha256": canonical_fingerprint(final_state),
        "final_evidence": final_state,
        "evaluation": {
            "passed": evaluation.passed,
            "components": evaluation.components,
            "checks": evaluation.checks,
            "diagnostics": evaluation.diagnostics,
            "failures": evaluation.failures,
        },
        "trajectory_diagnostics": _diagnose(
            turns=turns,
            evaluation=evaluation,
            failure_report=failure_report,
            prefix=prefix,
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


def run_live_native_agent(
    client: ChatClient,
    *,
    scenario_path: str | Path,
    credentials_path: str | Path,
    prefix_path: str | Path,
    failure_report_path: str | Path,
    max_turns: int = 15,
    execution_control: bool = False,
    output_path: str | Path | None = None,
    erpnext_base_url: str = "http://127.0.0.1:8080",
    container_cli: str = "docker",
) -> dict[str, Any]:
    root = repository_root()
    scenario = load_native_scenario(scenario_path)
    if scenario.raw.get("family") != (
        "erpnext-partial-return-replacement-reconciliation"
    ):
        raise ValueError(
            "run-native-model currently supports the partial-return family"
        )
    credentials = json.loads(
        Path(credentials_path).read_text(encoding="utf-8")
    )
    prefix = json.loads(Path(prefix_path).read_text(encoding="utf-8"))
    failure_report = json.loads(
        Path(failure_report_path).read_text(encoding="utf-8")
    )
    if failure_report["scenario_id"] != scenario.scenario_id:
        raise ValueError("failure report and scenario do not match")
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=erpnext_base_url,
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
        )
    )
    stack = ERPNextStack(
        compose_file=root / "runtimes" / "erpnext" / "compose.yaml",
        container_cli=container_cli,
        db_root_password=os.environ.get(
            "AFTERMATH_DB_ROOT_PASSWORD",
            "aftermath-root",
        ),
    )
    environment = ERPNextPartialReturnEnvironment(
        adapter=adapter,
        prefix=prefix,
        stack=stack,
        worker_control=default_worker_control(
            root,
            container_cli=container_cli,
        ),
        collector=ERPNextPartialReturnEvidenceCollector(adapter),
    )
    return run_native_return_agent(
        client,
        scenario=scenario,
        environment=environment,
        prefix=prefix,
        failure_report=failure_report,
        max_turns=max_turns,
        execution_control=execution_control,
        output_path=output_path,
    )
