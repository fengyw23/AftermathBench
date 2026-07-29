from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .core import canonical_fingerprint
from .scenarios.itsm_major_incident import (
    ITSM_VARIANTS,
    ITSMMajorIncidentEnv,
    build_itsm_failure_state,
    evaluate_itsm,
    verify_itsm_sql,
)
from .schema import load_task, repository_root


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]

    def as_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def as_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    text: str
    tool_calls: tuple[ToolCall, ...]
    raw_response: dict[str, Any]
    usage: dict[str, Any]
    stop_reason: str | None


class ChatClient(Protocol):
    provider: str
    model: str

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: tuple[ToolDefinition, ...],
    ) -> ModelTurn:
        ...


def _without_private_reasoning(value: Any) -> Any:
    private_keys = {
        "reasoning",
        "reasoning_content",
        "thinking",
        "chain_of_thought",
    }
    if isinstance(value, dict):
        return {
            key: _without_private_reasoning(item)
            for key, item in value.items()
            if key not in private_keys
        }
    if isinstance(value, list):
        return [
            _without_private_reasoning(item)
            for item in value
            if not (
                isinstance(item, dict)
                and item.get("type")
                in {"thinking", "redacted_thinking", "reasoning"}
            )
        ]
    return value


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


_INCIDENT_ID = {
    "incident_id": {
        "type": "string",
        "description": "Stable internal incident identifier.",
    }
}


ITSM_TOOL_DEFINITIONS = (
    ToolDefinition(
        "find_incident",
        "Read the authoritative parent or child incident record.",
        _object_schema(_INCIDENT_ID, ("incident_id",)),
    ),
    ToolDefinition(
        "find_affected_cis",
        "List configuration items linked as affected by an incident.",
        _object_schema(_INCIDENT_ID, ("incident_id",)),
    ),
    ToolDefinition(
        "find_incident_knowledge",
        "List knowledge articles and runbooks linked to an incident.",
        _object_schema(_INCIDENT_ID, ("incident_id",)),
    ),
    ToolDefinition(
        "find_child_incidents",
        "List child incidents and their current impact, urgency, and priority.",
        _object_schema(_INCIDENT_ID, ("incident_id",)),
    ),
    ToolDefinition(
        "find_incident_slas",
        "List every current and historical SLA record linked to an incident.",
        _object_schema(_INCIDENT_ID, ("incident_id",)),
    ),
    ToolDefinition(
        "find_sla_definitions",
        "List authoritative SLA definitions, priority applicability, and targets.",
        _object_schema({}),
    ),
    ToolDefinition(
        "find_notifications",
        "List notifications already created for an incident.",
        _object_schema(_INCIDENT_ID, ("incident_id",)),
    ),
    ToolDefinition(
        "get_escalation_job",
        "Read any persisted asynchronous major-incident escalation job.",
        _object_schema(_INCIDENT_ID, ("incident_id",)),
    ),
    ToolDefinition(
        "escalate_major_incident",
        (
            "Declare an existing incident as P1 and apply the standard major-"
            "incident SLA, child-priority, and manager-notification effects."
        ),
        _object_schema(_INCIDENT_ID, ("incident_id",)),
    ),
    ToolDefinition(
        "replace_with_critical_sla",
        "Replace a P1 incident's active noncritical SLA with the active P1 SLA.",
        _object_schema(_INCIDENT_ID, ("incident_id",)),
    ),
    ToolDefinition(
        "propagate_priority_to_children",
        "Propagate the parent P1 priority to all linked child incidents.",
        _object_schema(_INCIDENT_ID, ("incident_id",)),
    ),
    ToolDefinition(
        "send_major_incident_notification",
        "Send the required major-incident notification to the response manager.",
        _object_schema(_INCIDENT_ID, ("incident_id",)),
    ),
    ToolDefinition(
        "process_escalation_job",
        "Process a queued escalation job exactly once.",
        _object_schema(
            {
                "job_id": {
                    "type": "string",
                    "description": "Stable job identifier returned by the job query.",
                }
            },
            ("job_id",),
        ),
    ),
    ToolDefinition(
        "record_escalation_audit",
        "Record the required recovery audit after escalation state is reconciled.",
        _object_schema(_INCIDENT_ID, ("incident_id",)),
    ),
    ToolDefinition(
        "send_caller_update",
        "Send the required escalation update to the incident caller.",
        _object_schema(_INCIDENT_ID, ("incident_id",)),
    ),
    ToolDefinition(
        "close_escalation_review",
        "Close the recovery review after all escalation evidence is verified.",
        _object_schema(
            {
                "review_id": {
                    "type": "string",
                    "description": "Review identifier from the user request.",
                },
                **_INCIDENT_ID,
            },
            ("review_id", "incident_id"),
        ),
    ),
)


ITSM_SYSTEM_PROMPT = """You are an enterprise IT service-management agent.
Complete the user's still-valid request by acting through the supplied tools.
Treat tool and database records as authoritative. Investigate an ambiguous
failed write before deciding whether to retry, reconcile incomplete effects, or
continue. Preserve valid work already completed, satisfy linked business
records, avoid duplicate side effects, and do not delegate an objectively
decidable recovery choice back to the user. Stop when the requested state is
fully verified. You have at most {max_turns} model turns."""


def itsm_initial_message(
    *,
    task_path: str | Path | None = None,
    prefix_events: list[dict[str, Any]] | None = None,
    failure: dict[str, Any] | None = None,
) -> str:
    path = (
        Path(task_path)
        if task_path is not None
        else repository_root()
        / "data"
        / "tasks"
        / "itsm-major-incident-001"
        / "task.json"
    )
    raw = load_task(path).raw
    if prefix_events is None:
        prefix = [
            {
                "step": item["step"],
                "tool": item["tool"],
                "status": item["status"],
                "effect": item["effect"],
            }
            for item in raw["prefix_trace"]
        ]
    else:
        prefix = [
            {
                "step": item["sequence"],
                "tool": item["tool"],
                "arguments": item["arguments"],
                "result": item["result"],
            }
            for item in prefix_events
        ]
    latest_result = failure or raw["surface_failure"]["result"]
    packet = {
        "request": raw["user_instruction"],
        "successful_prior_tool_activity": prefix,
        "latest_tool_call": {
            "tool": raw["surface_failure"]["tool"],
            "arguments": raw["surface_failure"]["arguments"],
            "result": latest_result,
        },
    }
    return (
        "Continue this interrupted workflow from its current persistent state.\n"
        + json.dumps(packet, ensure_ascii=False, indent=2)
    )


class _HTTPJSONClient:
    def _post(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"model endpoint returned HTTP {error.code}: {body[:2000]}"
            ) from error


class OpenAICompatibleClient(_HTTPJSONClient):
    provider = "openai-compatible"

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        timeout: int = 120,
        extra_headers: dict[str, str] | None = None,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self.temperature = temperature

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: tuple[ToolDefinition, ...],
    ) -> ModelTurn:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "tools": [tool.as_openai() for tool in tools],
            "tool_choice": "auto",
            "temperature": self.temperature,
        }
        raw = self._post(
            f"{self.base_url}/chat/completions",
            payload,
            {
                "Authorization": f"Bearer {self.api_key}",
                **self.extra_headers,
            },
            self.timeout,
        )
        choice = raw["choices"][0]
        message = choice["message"]
        calls: list[ToolCall] = []
        for index, item in enumerate(message.get("tool_calls") or ()):
            function = item["function"]
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {
                    "__argument_parse_error__": function.get("arguments")
                }
            calls.append(
                ToolCall(
                    call_id=item.get("id") or f"call-{index}",
                    name=function["name"],
                    arguments=arguments,
                )
            )
        return ModelTurn(
            text=message.get("content") or "",
            tool_calls=tuple(calls),
            raw_response=raw,
            usage=raw.get("usage") or {},
            stop_reason=choice.get("finish_reason"),
        )


class AnthropicClient(_HTTPJSONClient):
    provider = "anthropic"

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
        timeout: int = 120,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_tokens = max_tokens

    def _messages(self, canonical: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        pending_results: list[dict[str, Any]] = []
        for message in canonical:
            role = message["role"]
            if role == "tool":
                pending_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": message["tool_call_id"],
                        "content": message["content"],
                    }
                )
                continue
            if pending_results:
                converted.append({"role": "user", "content": pending_results})
                pending_results = []
            if role == "assistant":
                content: list[dict[str, Any]] = []
                if message.get("content"):
                    content.append({"type": "text", "text": message["content"]})
                for call in message.get("tool_calls") or ():
                    content.append(
                        {
                            "type": "tool_use",
                            "id": call["id"],
                            "name": call["function"]["name"],
                            "input": json.loads(
                                call["function"].get("arguments") or "{}"
                            ),
                        }
                    )
                converted.append({"role": "assistant", "content": content})
            else:
                converted.append({"role": "user", "content": message["content"]})
        if pending_results:
            converted.append({"role": "user", "content": pending_results})
        return converted

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: tuple[ToolDefinition, ...],
    ) -> ModelTurn:
        payload = {
            "model": self.model,
            "system": system,
            "messages": self._messages(messages),
            "tools": [tool.as_anthropic() for tool in tools],
            "max_tokens": self.max_tokens,
            "temperature": 0,
        }
        raw = self._post(
            f"{self.base_url}/messages",
            payload,
            {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            self.timeout,
        )
        text_blocks: list[str] = []
        calls: list[ToolCall] = []
        for block in raw.get("content") or ():
            if block.get("type") == "text":
                text_blocks.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                calls.append(
                    ToolCall(
                        call_id=block["id"],
                        name=block["name"],
                        arguments=block.get("input") or {},
                    )
                )
        return ModelTurn(
            text="\n".join(text_blocks),
            tool_calls=tuple(calls),
            raw_response=raw,
            usage=raw.get("usage") or {},
            stop_reason=raw.get("stop_reason"),
        )


def _assistant_message(turn: ModelTurn) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": turn.text,
    }
    if turn.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(
                        call.arguments,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            }
            for call in turn.tool_calls
        ]
    return message


def _invoke_model_tool(
    environment: ITSMMajorIncidentEnv,
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


def run_itsm_agent(
    client: ChatClient,
    *,
    variant: str,
    seed_archive: str | Path | None = None,
    max_turns: int = 15,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    if max_turns < 1:
        raise ValueError("max_turns must be positive")
    environment, proxy, failure = build_itsm_failure_state(
        variant,
        seed_archive=seed_archive,
    )
    system = ITSM_SYSTEM_PROMPT.format(max_turns=max_turns)
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": itsm_initial_message(
                prefix_events=environment.event_log(),
                failure=failure,
            ),
        }
    ]
    model_turns: list[dict[str, Any]] = []
    stop_reason = "turn_limit"
    allowed_tools = {tool.name for tool in ITSM_TOOL_DEFINITIONS}
    try:
        for turn_index in range(1, max_turns + 1):
            turn = client.complete(
                system=system,
                messages=messages,
                tools=ITSM_TOOL_DEFINITIONS,
            )
            assistant = _assistant_message(turn)
            messages.append(assistant)
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
        evaluation = evaluate_itsm(environment)
        report = {
            "schema_version": "0.1",
            "run_id": (
                f"itsm-major-incident-001--{variant}--"
                f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
            ),
            "task_id": "itsm-major-incident-001",
            "variant": variant,
            "provider": client.provider,
            "model": client.model,
            "max_turns": max_turns,
            "stop_reason": stop_reason,
            "surface_failure": failure,
            "system_prompt": system,
            "initial_message": messages[0]["content"],
            "turns": model_turns,
            "fault_proxy_events": proxy.event_log(),
            "environment_tool_events": environment.event_log(),
            "final_state_sha256": canonical_fingerprint(final_state),
            "seed_provenance": final_state["seed_provenance"],
            "official_full_seed": (
                final_state["seed_provenance"][0][0]
                == "enterpriseops_full_seed"
            ),
            "evaluation": evaluation,
            "sql_verifier": verify_itsm_sql(environment),
        }
        if output_path is not None:
            destination = Path(output_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return report
    finally:
        environment.close()


def run_itsm_suite(
    client: ChatClient,
    *,
    seed_archive: str | Path | None,
    output_directory: str | Path,
    repetitions: int = 5,
    max_turns: int = 15,
) -> dict[str, Any]:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    root = Path(output_directory)
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", client.model)
    run_records: list[dict[str, Any]] = []
    for repetition in range(1, repetitions + 1):
        for variant in ITSM_VARIANTS:
            output = (
                root
                / safe_model
                / variant
                / f"repetition-{repetition:02d}.json"
            )
            try:
                report = run_itsm_agent(
                    client,
                    variant=variant,
                    seed_archive=seed_archive,
                    max_turns=max_turns,
                    output_path=output,
                )
                run_records.append(
                    {
                        "repetition": repetition,
                        "variant": variant,
                        "status": "completed",
                        "passed": report["evaluation"]["passed"],
                        "goal_completion": report["evaluation"]["goal_completion"],
                        "integrity": report["evaluation"]["integrity"],
                        "repair_completeness": report["evaluation"][
                            "repair_completeness"
                        ],
                        "preservation": report["evaluation"]["preservation"],
                        "protocol_safety": report["evaluation"]["protocol_safety"],
                        "turns": len(report["turns"]),
                        "trajectory": str(output),
                    }
                )
            except Exception as error:
                failure = {
                    "schema_version": "0.1",
                    "task_id": "itsm-major-incident-001",
                    "provider": client.provider,
                    "model": client.model,
                    "repetition": repetition,
                    "variant": variant,
                    "status": "run_error",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    json.dumps(failure, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                run_records.append({**failure, "trajectory": str(output)})

    completed = [item for item in run_records if item["status"] == "completed"]
    matched_successes = 0
    for repetition in range(1, repetitions + 1):
        group = [
            item
            for item in completed
            if item["repetition"] == repetition
        ]
        if (
            len(group) == len(ITSM_VARIANTS)
            and all(item["passed"] for item in group)
        ):
            matched_successes += 1
    summary = {
        "schema_version": "0.1",
        "task_id": "itsm-major-incident-001",
        "provider": client.provider,
        "model": client.model,
        "repetitions": repetitions,
        "expected_runs": repetitions * len(ITSM_VARIANTS),
        "completed_runs": len(completed),
        "run_errors": len(run_records) - len(completed),
        "task_pass_rate": (
            sum(bool(item["passed"]) for item in completed) / len(completed)
            if completed
            else None
        ),
        "matched_group_success_rate": matched_successes / repetitions,
        "component_pass_rates": {
            component: (
                sum(bool(item[component]) for item in completed) / len(completed)
                if completed
                else None
            )
            for component in (
                "goal_completion",
                "integrity",
                "repair_completeness",
                "preservation",
                "protocol_safety",
            )
        },
        "runs": run_records,
    }
    summary_path = root / safe_model / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def client_from_environment(
    *,
    provider: str,
    model: str,
    base_url: str | None,
    api_key_env: str,
    timeout_seconds: int | None = None,
) -> ChatClient:
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ValueError(f"environment variable {api_key_env!r} is not set")
    if provider == "openai-compatible":
        if not base_url:
            raise ValueError("--base-url is required for openai-compatible")
        kwargs: dict[str, Any] = {}
        if timeout_seconds is not None:
            kwargs["timeout"] = timeout_seconds
        return OpenAICompatibleClient(
            model=model,
            base_url=base_url,
            api_key=api_key,
            **kwargs,
        )
    if provider == "anthropic":
        kwargs = {}
        if timeout_seconds is not None:
            kwargs["timeout"] = timeout_seconds
        return AnthropicClient(
            model=model,
            base_url=base_url or "https://api.anthropic.com/v1",
            api_key=api_key,
            **kwargs,
        )
    raise ValueError(f"unsupported provider: {provider}")
