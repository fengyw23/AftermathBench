import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from aftermath_bench.erpnext_model_runner import (
    ERP_NEXT_TOOL_DEFINITIONS,
    erpnext_initial_message,
    run_erpnext_agent,
)
from aftermath_bench.integrations.erpnext_evaluator import ERPNextEvaluation
from aftermath_bench.model_runner import ModelTurn, ToolCall


class _ScriptedClient:
    provider = "scripted-test"
    model = "erpnext-investigator"

    def __init__(self) -> None:
        self.turn = 0

    def complete(self, **_kwargs: Any) -> ModelTurn:
        self.turn += 1
        scripts = {
            1: (
                ToolCall(
                    "q1",
                    "get_payment_entry",
                    {"payment_entry": "ACC-PAY-1"},
                ),
                ToolCall(
                    "q2",
                    "find_remittance_jobs",
                    {"payment_entry": "ACC-PAY-1"},
                ),
                ToolCall(
                    "q3",
                    "get_remittance_delivery",
                    {"payment_entry": "ACC-PAY-1"},
                ),
            ),
            2: (),
        }
        return ModelTurn(
            text="verified" if self.turn == 2 else "",
            tool_calls=scripts[self.turn],
            raw_response={
                "turn": self.turn,
                "reasoning_content": "private",
            },
            usage={},
            stop_reason="stop" if self.turn == 2 else "tool_calls",
        )


class _FakeEnvironment:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def invoke(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        result = {"ok": True, "tool": tool, **kwargs}
        self.events.append(
            {
                "kind": "tool",
                "tool": tool,
                "arguments": kwargs,
                "result": result,
            }
        )
        return result

    def snapshot(self) -> dict[str, Any]:
        return {"stable": True}

    def event_log(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.events)


def _prefix() -> dict[str, Any]:
    return {
        "purchase_order": "PUR-ORD-1",
        "purchase_receipt": "MAT-PRE-1",
        "purchase_invoice": "ACC-PINV-1",
        "payment_entry": "ACC-PAY-1",
        "protected_fingerprints": {
            "purchase_order": "po",
            "purchase_receipt": "pr",
            "purchase_invoice": "pi",
        },
        "trace": [
            {
                "kind": "write",
                "tool": "create Purchase Order",
                "name": "PUR-ORD-1",
            },
            {
                "kind": "write",
                "tool": "submit Purchase Order",
                "name": "PUR-ORD-1",
            },
        ],
    }


def _failure_report() -> dict[str, Any]:
    return {
        "visible_failure": {
            "ok": False,
            "error": "connection_lost_before_confirmation",
        },
        "failure_boundary_evidence": {
            "payment_entries": [{"name": "ACC-PAY-1", "docstatus": 1}],
            "remittance": None,
        },
    }


class ERPNextModelRunnerTest(unittest.TestCase):
    def test_model_input_does_not_reveal_hidden_variant(self) -> None:
        message = erpnext_initial_message(
            prefix=_prefix(),
            failure_report=_failure_report(),
        )
        self.assertIn("ACC-PINV-1", message)
        self.assertIn("connection_lost_before_confirmation", message)
        for variant in (
            "request_not_reached",
            "database_committed_response_lost",
            "after_commit_enqueue_failed",
            "async_job_pending",
        ):
            self.assertNotIn(variant, message)

    def test_every_exposed_tool_has_a_closed_schema(self) -> None:
        names = set()
        for tool in ERP_NEXT_TOOL_DEFINITIONS:
            self.assertNotIn(tool.name, names)
            names.add(tool.name)
            self.assertTrue(tool.description)
            self.assertEqual(tool.input_schema["type"], "object")
            self.assertFalse(tool.input_schema["additionalProperties"])

    @patch(
        "aftermath_bench.erpnext_model_runner.evaluate_erpnext_recovery"
    )
    def test_scripted_run_records_queries_and_strips_private_reasoning(
        self,
        evaluate,
    ) -> None:
        evaluate.return_value = ERPNextEvaluation(
            passed=True,
            checks={"complete": True},
            diagnostics={"test": True},
        )
        with TemporaryDirectory() as directory:
            output = Path(directory) / "run.json"
            report = run_erpnext_agent(
                _ScriptedClient(),
                environment=_FakeEnvironment(),
                variant="database_committed_response_lost",
                prefix=_prefix(),
                failure_report=_failure_report(),
                output_path=output,
            )
            self.assertTrue(report["evaluation"]["passed"])
            diagnostics = report["trajectory_diagnostics"]
            self.assertTrue(diagnostics["inspected_payment_state"])
            self.assertTrue(diagnostics["inspected_remittance_state"])
            self.assertEqual(diagnostics["mutation_tool_count"], 0)
            serialized = output.read_text(encoding="utf-8")
            self.assertNotIn("private", serialized)


if __name__ == "__main__":
    unittest.main()
