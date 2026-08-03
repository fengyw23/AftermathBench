from __future__ import annotations

import unittest
from typing import Any

from aftermath_bench.integrations.erpnext_return_agent import (
    settle_document_webhook_delivery,
)


class ScriptedCall:
    def __init__(self, *, grace_delivered: bool, jobs: list[dict[str, Any]]) -> None:
        self.grace_delivered = grace_delivered
        self.jobs = jobs
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((tool, kwargs))
        if tool == "get_external_delivery":
            return {"ok": True, "delivered": False}
        if tool == "wait_for_external_delivery":
            delivered = self.grace_delivered or kwargs["timeout_seconds"] == 30
            return {"ok": True, "delivered": delivered}
        if tool == "find_background_jobs":
            return {"ok": True, "jobs": self.jobs}
        return {"ok": True}


class ERPNextWebhookSettlementTests(unittest.TestCase):
    def test_native_delivery_during_grace_period_is_not_enqueued_twice(self) -> None:
        call = ScriptedCall(grace_delivered=True, jobs=[])

        result = settle_document_webhook_delivery(
            call,
            doctype="Stock Entry",
            name="STE-1",
            webhook_name="Arrival",
        )

        self.assertTrue(result["delivered"])
        self.assertEqual(
            [tool for tool, _ in call.calls],
            ["get_external_delivery", "wait_for_external_delivery"],
        )

    def test_missing_native_job_is_enqueued_after_grace_period(self) -> None:
        call = ScriptedCall(grace_delivered=False, jobs=[])

        settle_document_webhook_delivery(
            call,
            doctype="Stock Entry",
            name="STE-1",
            webhook_name="Arrival",
        )

        self.assertEqual(
            [tool for tool, _ in call.calls],
            [
                "get_external_delivery",
                "wait_for_external_delivery",
                "find_background_jobs",
                "enqueue_document_webhook",
                "wait_for_external_delivery",
            ],
        )

    def test_pending_native_job_is_resumed_instead_of_duplicated(self) -> None:
        call = ScriptedCall(
            grace_delivered=False,
            jobs=[{"status": "queued"}],
        )

        settle_document_webhook_delivery(
            call,
            doctype="Stock Entry",
            name="STE-1",
            webhook_name="Arrival",
        )

        tools = [tool for tool, _ in call.calls]
        self.assertIn("resume_workers", tools)
        self.assertNotIn("enqueue_document_webhook", tools)


if __name__ == "__main__":
    unittest.main()
