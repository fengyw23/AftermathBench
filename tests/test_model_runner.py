import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from aftermath_bench.model_runner import (
    AnthropicClient,
    ITSM_TOOL_DEFINITIONS,
    ModelTurn,
    OpenAICompatibleClient,
    ToolCall,
    itsm_initial_message,
    run_itsm_agent,
    run_itsm_suite,
)


class ScriptedClient:
    provider = "scripted-test"
    model = "evidence-driven-script"

    def __init__(self) -> None:
        self.turn = 0

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: tuple[Any, ...],
    ) -> ModelTurn:
        self.turn += 1
        incident_id = "inc-major-001"
        scripts = {
            1: (
                ToolCall("q1", "find_incident", {"incident_id": incident_id}),
                ToolCall("q2", "find_child_incidents", {"incident_id": incident_id}),
                ToolCall("q3", "find_incident_slas", {"incident_id": incident_id}),
                ToolCall("q4", "find_notifications", {"incident_id": incident_id}),
                ToolCall("q5", "get_escalation_job", {"incident_id": incident_id}),
            ),
            2: (
                ToolCall(
                    "w1",
                    "escalate_major_incident",
                    {"incident_id": incident_id},
                ),
            ),
            3: (
                ToolCall(
                    "w2",
                    "record_escalation_audit",
                    {"incident_id": incident_id},
                ),
                ToolCall(
                    "w3",
                    "send_caller_update",
                    {"incident_id": incident_id},
                ),
                ToolCall(
                    "w4",
                    "close_escalation_review",
                    {"review_id": "review-001", "incident_id": incident_id},
                ),
            ),
            4: (),
        }
        return ModelTurn(
            text="verified" if self.turn == 4 else "",
            tool_calls=scripts[self.turn],
            raw_response={
                "scripted_turn": self.turn,
                "reasoning_content": "private-test-content",
            },
            usage={"input_tokens": 0, "output_tokens": 0},
            stop_reason="stop" if self.turn == 4 else "tool_calls",
        )


class StopImmediatelyClient:
    provider = "scripted-test"
    model = "stop-immediately"

    def complete(self, **_kwargs: Any) -> ModelTurn:
        return ModelTurn(
            text="done",
            tool_calls=(),
            raw_response={"scripted": True},
            usage={},
            stop_reason="stop",
        )


class ModelRunnerTest(unittest.TestCase):
    def test_model_input_does_not_reveal_hidden_variant(self) -> None:
        message = itsm_initial_message()
        self.assertIn("504 Gateway Timeout", message)
        self.assertNotIn("not_committed", message)
        self.assertNotIn("partial_commit", message)
        self.assertNotIn("async_pending", message)

    def test_every_exposed_tool_has_closed_json_schema(self) -> None:
        names = set()
        for tool in ITSM_TOOL_DEFINITIONS:
            self.assertNotIn(tool.name, names)
            names.add(tool.name)
            self.assertTrue(tool.description)
            self.assertEqual(tool.input_schema["type"], "object")
            self.assertFalse(tool.input_schema["additionalProperties"])

    def test_scripted_agent_produces_replayable_report(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "run.json"
            report = run_itsm_agent(
                ScriptedClient(),
                variant="not_committed",
                output_path=output,
            )
            self.assertTrue(report["evaluation"]["passed"])
            self.assertEqual(report["stop_reason"], "model_stopped")
            self.assertEqual(len(report["turns"]), 4)
            self.assertTrue(output.exists())
            serialized = output.read_text("utf-8")
            self.assertIn("environment_tool_events", serialized)
            self.assertNotIn("private-test-content", serialized)

    def test_suite_aggregates_all_matched_variants(self) -> None:
        with TemporaryDirectory() as directory:
            summary = run_itsm_suite(
                StopImmediatelyClient(),
                seed_archive=None,
                output_directory=directory,
                repetitions=1,
            )
            self.assertEqual(summary["completed_runs"], 4)
            self.assertEqual(summary["run_errors"], 0)
            self.assertEqual(summary["task_pass_rate"], 0)
            self.assertEqual(summary["matched_group_success_rate"], 0)

    def test_openai_compatible_tool_call_is_normalized(self) -> None:
        client = OpenAICompatibleClient(
            model="test-model",
            base_url="https://example.invalid/v1",
            api_key="not-a-real-key",
        )
        client._post = lambda *_args, **_kwargs: {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "find_incident",
                                    "arguments": '{"incident_id":"inc-major-001"}',
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        turn = client.complete(
            system="test",
            messages=[{"role": "user", "content": "test"}],
            tools=ITSM_TOOL_DEFINITIONS,
        )
        self.assertEqual(turn.tool_calls[0].name, "find_incident")
        self.assertEqual(
            turn.tool_calls[0].arguments,
            {"incident_id": "inc-major-001"},
        )

    def test_anthropic_tool_call_is_normalized(self) -> None:
        client = AnthropicClient(
            model="test-model",
            api_key="not-a-real-key",
            base_url="https://example.invalid/v1",
        )
        client._post = lambda *_args, **_kwargs: {
            "content": [
                {"type": "text", "text": "checking"},
                {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "find_incident_slas",
                    "input": {"incident_id": "inc-major-001"},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        turn = client.complete(
            system="test",
            messages=[{"role": "user", "content": "test"}],
            tools=ITSM_TOOL_DEFINITIONS,
        )
        self.assertEqual(turn.text, "checking")
        self.assertEqual(turn.tool_calls[0].name, "find_incident_slas")


if __name__ == "__main__":
    unittest.main()
