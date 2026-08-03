from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .core import canonical_fingerprint
from .formal_evidence_builder import verify_formal_input_lock
from .hidden_test_eligibility import (
    HiddenEvaluationSession,
    begin_hidden_test_evaluation,
    consume_hidden_test_evaluation,
    validate_hidden_evaluation_session,
)
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
from .native_boundary_equivalence import native_boundaries_equivalent
from .native_erpnext_manufacturing_family import ERP_NEXT_MANUFACTURING_FAMILY
from .native_erpnext_multiwarehouse_family import ERP_NEXT_MULTIWAREHOUSE_FAMILY
from .native_family import (
    NativeFamilyDefinition,
    NativeFamilyRegistry,
    NativeRuntimeContext,
)
from .native_forgejo_family import FORGEJO_RELEASE_FAMILY
from .native_forgejo_migration_family import FORGEJO_MIGRATION_FAMILY
from .native_forgejo_package_provenance_family import (
    FORGEJO_PACKAGE_PROVENANCE_FAMILY,
)
from .native_forgejo_publication_family import FORGEJO_PUBLICATION_FAMILY
from .native_kubernetes_constraint_family import KUBERNETES_CONSTRAINT_FAMILY
from .native_kubernetes_family import KUBERNETES_ROLLOUT_FAMILY
from .native_kubernetes_interaction_family import KUBERNETES_INTERACTION_FAMILY
from .native_kubernetes_migration_family import KUBERNETES_MIGRATION_FAMILY
from .native_kubernetes_settlement_family import (
    KUBERNETES_SETTLEMENT_FAMILY,
)
from .native_kubernetes_settlement_v2_family import (
    KUBERNETES_SETTLEMENT_V2_FAMILY,
)
from .native_sales_family import SALES_RETURN_FAMILY
from .native_scenario import NativeScenario, load_native_scenario
from .path_safety import safe_relative_path
from .schema import repository_root
from .strict_json import load_json_strict

NATIVE_SYSTEM_PROMPT = """\
You are an enterprise operations agent working in a live ERPNext environment.
A step in a long procurement workflow returned an error after earlier
operations had already produced persistent effects. Complete the user's
still-valid goal while preserving valid prior effects.

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
            "Webhook",
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
        "list_related_documents",
        (
            "Read documents connected by one native ERPNext link. The tool "
            "returns the full target documents and the exact field paths that "
            "matched; it does not follow multiple hops or recommend actions."
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
            "Purchase Receipt, and ensure there is exactly one active "
            "replacement invoice linked to that replacement receipt. Search "
            "the Purchase Invoices before any invoice creation: if one linked "
            "draft already exists, reuse and submit it; create one only after "
            "confirming that none exists, and never create a second. Reconcile "
            "the supplier debit credit to that replacement invoice and ensure "
            "the pickup event is delivered exactly once. First inspect the "
            "current Return, job, delivery, and linked-invoice state; perform "
            "only missing writes, then verify the relevant documents and "
            "ledgers."
        )
    return message


def _invoke_tool(
    environment: Any,
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


def _surface_failure(failure_report: dict[str, Any]) -> dict[str, Any]:
    """Normalize the validated native boundary-report layouts."""

    direct = failure_report.get("visible_failure")
    if isinstance(direct, dict):
        return dict(direct)
    latest_attempt = failure_report.get("latest_attempt")
    if isinstance(latest_attempt, dict):
        result = latest_attempt.get("result")
        if isinstance(result, dict):
            return dict(result)
    raise ValueError(
        "native failure report must contain visible_failure or "
        "latest_attempt.result"
    )


def _diagnose(
    *,
    turns: list[dict[str, Any]],
    evaluation: Any,
    failure_report: dict[str, Any],
    prefix: dict[str, Any],
) -> dict[str, Any]:
    calls = [call for turn in turns for call in turn["tool_calls"]]
    names = [call["name"] for call in calls]
    query_names = [name for name in names if name not in NATIVE_RETURN_MUTATIONS]
    mutation_names = [name for name in names if name in NATIVE_RETURN_MUTATIONS]
    boundary_return = failure_report.get(
        "failure_boundary_evidence",
        {},
    ).get("purchase_return", {})
    boundary_replacement_invoices = [
        invoice
        for invoice in failure_report.get(
            "failure_boundary_evidence",
            {},
        ).get("replacement_invoices", [])
        if int(invoice.get("docstatus", 0)) != 2
    ]
    existing_replacement_invoice_names = {
        str(invoice.get("name"))
        for invoice in boundary_replacement_invoices
        if invoice.get("name")
    }
    create_invoice_positions = [
        index
        for index, call in enumerate(calls)
        if call["name"] == "create_purchase_invoice_from_receipt"
        and call["arguments"].get("purchase_receipt")
        == prefix.get("replacement_purchase_receipt")
    ]
    first_create_invoice_position = (
        min(create_invoice_positions) if create_invoice_positions else None
    )
    calls_before_invoice_create = (
        calls[:first_create_invoice_position]
        if first_create_invoice_position is not None
        else calls
    )
    queried_linked_invoices = any(
        (
            call["name"] == "list_documents"
            and call["arguments"].get("doctype") == "Purchase Invoice"
        )
        or (
            call["name"] == "list_related_documents"
            and call["arguments"].get("source_doctype") == "Purchase Receipt"
            and call["arguments"].get("source_name")
            == prefix.get("replacement_purchase_receipt")
            and call["arguments"].get("target_doctype") == "Purchase Invoice"
        )
        or (
            call["name"] == "get_document"
            and call["arguments"].get("doctype") == "Purchase Invoice"
            and str(call["arguments"].get("name")) in existing_replacement_invoice_names
        )
        for call in calls_before_invoice_create
    )
    created_without_linked_invoice_investigation = bool(
        boundary_replacement_invoices
        and create_invoice_positions
        and not queried_linked_invoices
    )
    unsafe_retry = int(boundary_return.get("docstatus", 0)) == 1 and any(
        call["name"] == "submit_document"
        and call["arguments"].get("name") == prefix["purchase_return"]
        for call in calls
    )
    evidence_groups = {
        "documents": (
            "get_document" in query_names
            or "list_documents" in query_names
            or "list_related_documents" in query_names
        ),
        "ledger": (
            "get_stock_ledger" in query_names or "get_general_ledger" in query_names
        ),
        "async": (
            "find_background_jobs" in query_names
            and "get_external_delivery" in query_names
        ),
        "linked_invoices": (
            queried_linked_invoices
            or not boundary_replacement_invoices
            or not create_invoice_positions
        ),
    }
    # Error attribution explains failed runs.  A successful terminal state
    # must not be relabelled as an investigation failure merely because the
    # model reached it without issuing every diagnostic query.
    if evaluation.passed:
        primary_error = None
    elif unsafe_retry:
        primary_error = "state_inference_failure"
    elif created_without_linked_invoice_investigation or not (
        evidence_groups["documents"] and evidence_groups["async"]
    ):
        primary_error = "investigation_failure"
    elif (
        not evaluation.components["preservation"]
        or not evaluation.components["protocol_safety"]
    ):
        primary_error = "scope_failure"
    elif (
        not evaluation.components["goal_completion"]
        or not evaluation.components["repair_completeness"]
    ):
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
        "boundary_active_replacement_invoice_count": len(boundary_replacement_invoices),
        "queried_linked_invoices_before_create": (queried_linked_invoices),
        "created_invoice_without_linked_invoice_investigation": (
            created_without_linked_invoice_investigation
        ),
        "tool_error_count": len(tool_errors),
        "tool_errors": tool_errors,
    }


def run_native_family_agent(
    client: ChatClient,
    *,
    family: NativeFamilyDefinition,
    scenario: NativeScenario,
    environment: Any,
    prefix: dict[str, Any],
    failure_report: dict[str, Any],
    max_turns: int = 25,
    execution_control: bool = False,
    output_path: str | Path | None = None,
    hidden_evaluation_session: HiddenEvaluationSession | None = None,
    hidden_freeze_path: str | Path | None = None,
    formal_input_lock_verification: dict[str, Any] | None = None,
    pre_model_boundary_evidence: dict[str, str] | None = None,
) -> dict[str, Any]:
    if scenario.split == "hidden_test":
        if hidden_evaluation_session is None or hidden_freeze_path is None:
            raise RuntimeError(
                "hidden-test provider access requires a runner-managed "
                "evaluation lock"
            )
        if (
            hidden_evaluation_session.provider != str(client.provider)
            or hidden_evaluation_session.model != str(client.model)
            or hidden_evaluation_session.execution_control
            is not execution_control
        ):
            raise RuntimeError(
                "hidden evaluation lock does not match this model run"
            )
        validate_hidden_evaluation_session(
            scenario_path=scenario.path,
            freeze_path=Path(hidden_freeze_path),
            session=hidden_evaluation_session,
        )
    elif hidden_evaluation_session is not None or hidden_freeze_path is not None:
        raise ValueError(
            "hidden evaluation evidence was supplied for a non-hidden scenario"
        )
    system = family.system_prompt.format(max_turns=max_turns)
    initial = family.build_initial_message(
        scenario=scenario,
        prefix=prefix,
        failure_report=failure_report,
        execution_control=execution_control,
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": initial}]
    turns: list[dict[str, Any]] = []
    stop_reason = "turn_limit"
    allowed_tools = {definition.name for definition in family.tool_definitions}
    for turn_index in range(1, max_turns + 1):
        turn = client.complete(
            system=system,
            messages=messages,
            tools=family.tool_definitions,
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
    evaluation = family.evaluate(final_state, prefix)
    report = {
        "schema_version": "0.6",
        "run_id": (
            f"{scenario.scenario_id}--{failure_report['variant']}--"
            f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        ),
        "scenario_id": scenario.scenario_id,
        "instance_id": scenario.instance_id,
        "family": family.family_id,
        "domain": family.domain,
        "variant": failure_report["variant"],
        "provider": client.provider,
        "model": client.model,
        "max_turns": max_turns,
        "execution_control": execution_control,
        "stop_reason": stop_reason,
        "surface_failure": _surface_failure(failure_report),
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
        "trajectory_diagnostics": family.diagnose(
            turns=turns,
            evaluation=evaluation,
            failure_report=failure_report,
            prefix=prefix,
        ),
    }
    instance_spec_sha256 = scenario.raw.get("instance_spec_sha256")
    if isinstance(instance_spec_sha256, str) and instance_spec_sha256:
        report["instance_spec_sha256"] = instance_spec_sha256
    if formal_input_lock_verification is not None:
        report["formal_input_lock"] = dict(
            formal_input_lock_verification
        )
    if pre_model_boundary_evidence is not None:
        report["pre_model_boundary_evidence"] = dict(
            pre_model_boundary_evidence
        )
    if hidden_evaluation_session is not None:
        report["hidden_evaluation"] = {
            "evaluation_id": hidden_evaluation_session.evaluation_id,
            "lock_event_sha256": (
                hidden_evaluation_session.lock_event_sha256
            ),
            "consumed_event_sha256": None,
        }
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report


def _build_partial_return_environment(
    context: NativeRuntimeContext,
) -> ERPNextPartialReturnEnvironment:
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
    return ERPNextPartialReturnEnvironment(
        adapter=adapter,
        prefix=context.prefix,
        stack=stack,
        worker_control=default_worker_control(
            context.repository_root,
            container_cli=context.container_cli,
        ),
        collector=ERPNextPartialReturnEvidenceCollector(adapter),
    )


PARTIAL_RETURN_FAMILY = NativeFamilyDefinition(
    family_id="erpnext-partial-return-replacement-reconciliation",
    domain="erpnext",
    system_prompt=NATIVE_SYSTEM_PROMPT,
    tool_definitions=NATIVE_RETURN_TOOL_DEFINITIONS,
    mutation_tools=frozenset(NATIVE_RETURN_MUTATIONS),
    build_environment=_build_partial_return_environment,
    build_initial_message=native_initial_message,
    evaluate=lambda final_state, prefix: evaluate_partial_return_recovery(
        final_state,
        prefix=prefix,
    ),
    diagnose=_diagnose,
)


NATIVE_FAMILY_REGISTRY = NativeFamilyRegistry(
    (
        PARTIAL_RETURN_FAMILY,
        SALES_RETURN_FAMILY,
        ERP_NEXT_MANUFACTURING_FAMILY,
        ERP_NEXT_MULTIWAREHOUSE_FAMILY,
        FORGEJO_RELEASE_FAMILY,
        FORGEJO_MIGRATION_FAMILY,
        FORGEJO_PUBLICATION_FAMILY,
        FORGEJO_PACKAGE_PROVENANCE_FAMILY,
        KUBERNETES_ROLLOUT_FAMILY,
        KUBERNETES_SETTLEMENT_FAMILY,
        KUBERNETES_SETTLEMENT_V2_FAMILY,
        KUBERNETES_MIGRATION_FAMILY,
        KUBERNETES_CONSTRAINT_FAMILY,
        KUBERNETES_INTERACTION_FAMILY,
    )
)


def run_native_return_agent(
    client: ChatClient,
    *,
    scenario: NativeScenario,
    environment: ERPNextPartialReturnEnvironment,
    prefix: dict[str, Any],
    failure_report: dict[str, Any],
    max_turns: int = 25,
    execution_control: bool = False,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Backward-compatible entry point for the first native family."""
    return run_native_family_agent(
        client,
        family=PARTIAL_RETURN_FAMILY,
        scenario=scenario,
        environment=environment,
        prefix=prefix,
        failure_report=failure_report,
        max_turns=max_turns,
        execution_control=execution_control,
        output_path=output_path,
    )


def _pre_model_boundary_matches_lock(
    *,
    root: Path,
    family_id: str,
    locked_boundary_sha256: str,
    locked_boundary_path: str | None,
    evidence_path: Path,
    evidence_sha256: str,
) -> bool:
    if evidence_sha256 == locked_boundary_sha256:
        return True
    try:
        locked_path = safe_relative_path(
            root,
            str(locked_boundary_path or ""),
            required_prefix="data",
            must_exist=True,
            require_file=True,
        )
        locked_boundary = load_json_strict(locked_path)
        live_boundary = load_json_strict(evidence_path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return False
    return (
        isinstance(locked_boundary, dict)
        and isinstance(live_boundary, dict)
        and native_boundaries_equivalent(
            family_id,
            locked_boundary,
            live_boundary,
        )
    )


def run_live_native_agent(
    client: ChatClient,
    *,
    scenario_path: str | Path,
    credentials_path: str | Path,
    prefix_path: str | Path,
    failure_report_path: str | Path,
    max_turns: int = 25,
    execution_control: bool = False,
    output_path: str | Path | None = None,
    erpnext_base_url: str = "http://127.0.0.1:8080",
    container_cli: str = "docker",
    hidden_freeze_path: str | Path | None = None,
    hidden_usage_ledger_path: str | Path | None = None,
    hidden_evaluation_id: str | None = None,
    hidden_finalize: bool = False,
    formal_input_lock_path: str | Path | None = None,
    pre_model_boundary_evidence_path: str | Path | None = None,
) -> dict[str, Any]:
    root = repository_root()
    scenario = load_native_scenario(scenario_path)
    family = NATIVE_FAMILY_REGISTRY.get(str(scenario.raw.get("family", "")))
    credentials = json.loads(Path(credentials_path).read_text(encoding="utf-8"))
    prefix = json.loads(Path(prefix_path).read_text(encoding="utf-8"))
    failure_report = json.loads(Path(failure_report_path).read_text(encoding="utf-8"))

    validate_native_run_bindings(
        scenario=scenario,
        prefix=prefix,
        failure_report=failure_report,
        family_id=family.family_id,
    )
    # Normalize every family-specific boundary layout before a hidden-test
    # lifecycle is locked and, crucially, before any provider can see it.
    _surface_failure(failure_report)
    if (
        pre_model_boundary_evidence_path is not None
        and formal_input_lock_path is None
    ):
        raise ValueError(
            "pre-model boundary evidence requires --formal-input-lock"
        )
    formal_input_lock_verification: dict[str, Any] | None = None
    pre_model_boundary_evidence: dict[str, str] | None = None
    if formal_input_lock_path is not None:
        verified_input_lock = verify_formal_input_lock(
            formal_input_lock_path,
            root=root,
            scenario_id=scenario.scenario_id,
            domain_id=scenario.domain_id,
            family_id=scenario.family_id,
            instance_id=scenario.instance_id,
            variant_id=str(failure_report["variant"]),
            failure_report_path=failure_report_path,
            prefix_path=prefix_path,
        )
        formal_input_lock_verification = verified_input_lock.as_dict()
        if pre_model_boundary_evidence_path is None:
            raise ValueError(
                "formal input lock requires "
                "--pre-model-boundary-evidence"
            )
        evidence_path = Path(pre_model_boundary_evidence_path)
        if not evidence_path.is_file() or evidence_path.is_symlink():
            raise ValueError(
                "pre-model boundary evidence must be a regular file"
            )
        digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        if not _pre_model_boundary_matches_lock(
            root=root,
            family_id=family.family_id,
            locked_boundary_sha256=formal_input_lock_verification[
                "boundary_state_sha256"
            ],
            locked_boundary_path=getattr(
                verified_input_lock,
                "boundary_state_path",
                None,
            ),
            evidence_path=evidence_path,
            evidence_sha256=digest,
        ):
            raise ValueError(
                "pre-model live boundary evidence does not match "
                "the formal input lock"
            )
        pre_model_boundary_evidence = {
            "variant_id": str(failure_report["variant"]),
            "source_basename": evidence_path.name,
            "sha256": digest,
        }
    environment = family.build_environment(
        NativeRuntimeContext(
            scenario=scenario,
            credentials=credentials,
            prefix=prefix,
            failure_report=failure_report,
            repository_root=root,
            base_url=erpnext_base_url,
            container_cli=container_cli,
        )
    )
    hidden_session: HiddenEvaluationSession | None = None
    if scenario.split == "hidden_test":
        if (
            hidden_freeze_path is None
            or hidden_usage_ledger_path is None
            or hidden_evaluation_id is None
        ):
            raise RuntimeError(
                "hidden-test runs require --hidden-freeze, "
                "--hidden-usage-ledger and --hidden-evaluation-id"
            )
        hidden_session = begin_hidden_test_evaluation(
            scenario_path=scenario.path,
            freeze_path=Path(hidden_freeze_path),
            usage_ledger_path=Path(hidden_usage_ledger_path),
            evaluation_id=hidden_evaluation_id,
            provider=str(client.provider),
            model=str(client.model),
            execution_control=execution_control,
        )
    elif any(
        value is not None
        for value in (
            hidden_freeze_path,
            hidden_usage_ledger_path,
            hidden_evaluation_id,
        )
    ) or hidden_finalize:
        raise ValueError(
            "hidden evaluation options are valid only for hidden_test scenarios"
        )
    report = run_native_family_agent(
        client,
        family=family,
        scenario=scenario,
        environment=environment,
        prefix=prefix,
        failure_report=failure_report,
        max_turns=max_turns,
        execution_control=execution_control,
        output_path=output_path,
        hidden_evaluation_session=hidden_session,
        hidden_freeze_path=hidden_freeze_path,
        formal_input_lock_verification=formal_input_lock_verification,
        pre_model_boundary_evidence=pre_model_boundary_evidence,
    )
    if hidden_session is not None and hidden_finalize:
        consumed = consume_hidden_test_evaluation(
            scenario_path=scenario.path,
            freeze_path=Path(hidden_freeze_path),
            session=hidden_session,
        )
        report["hidden_evaluation"]["consumed_event_sha256"] = consumed[
            "event_sha256"
        ]
        if output_path is not None:
            destination = Path(output_path)
            destination.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    return report


def validate_native_run_bindings(
    *,
    scenario: NativeScenario,
    prefix: dict[str, Any],
    failure_report: dict[str, Any],
    family_id: str,
) -> None:
    """Reject cross-wired native inputs before any provider request."""

    if failure_report["scenario_id"] != scenario.scenario_id:
        raise ValueError("failure report and scenario do not match")
    prefix_scenario_id = prefix.get("scenario_id")
    if (
        prefix_scenario_id is not None
        and str(prefix_scenario_id) != scenario.scenario_id
    ):
        raise ValueError("prefix and scenario do not match")
    if str(failure_report.get("variant", "")) not in scenario.variants:
        raise ValueError("failure report variant is not declared by scenario")
    instance_hashes = {
        str(value)
        for value in (
            scenario.raw.get("instance_spec_sha256"),
            prefix.get("instance_spec_sha256"),
            failure_report.get("instance_spec_sha256"),
        )
        if value is not None
    }
    instance_bound_families = {
        "forgejo-release-package-publication",
        "forgejo-migration-deployment",
    }
    if (
        family_id in instance_bound_families
        and any(
            value is None
            for value in (
                scenario.raw.get("instance_spec_sha256"),
                prefix.get("instance_spec_sha256"),
                failure_report.get("instance_spec_sha256"),
            )
        )
    ):
        raise ValueError(
            "Forgejo instance-bound inputs must all bind the instance spec"
        )
    if len(instance_hashes) > 1:
        raise ValueError(
            "scenario, prefix and failure report instance specs do not match"
        )
