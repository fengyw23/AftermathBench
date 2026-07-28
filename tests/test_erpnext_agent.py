import unittest
from unittest.mock import Mock, patch

from aftermath_bench.integrations.erpnext_agent import (
    ERPNextRecoveryEnvironment,
    reference_erpnext_recovery,
)
from aftermath_bench.integrations.erpnext_evidence import ProcurementPaymentIDs


class _ReferenceFixture:
    def __init__(self, *, docstatus, delivered, jobs):
        self.ids = ProcurementPaymentIDs("PO-1", "PR-1", "PI-1")
        self.payment_entry = "PAY-1"
        self.docstatus = docstatus
        self.delivered = delivered
        self.jobs = jobs
        self.calls = []

    def invoke(self, tool, **kwargs):
        self.calls.append((tool, kwargs))
        if tool == "get_purchase_order":
            return {"ok": True, "document": {"name": "PO-1"}}
        if tool == "get_purchase_receipt":
            return {"ok": True, "document": {"name": "PR-1"}}
        if tool == "get_purchase_invoice":
            return {"ok": True, "document": {"name": "PI-1"}}
        if tool == "get_payment_entry":
            return {
                "ok": True,
                "document": {"name": "PAY-1", "docstatus": self.docstatus},
            }
        if tool == "find_payments_for_invoice":
            return {"ok": True, "payments": []}
        if tool == "get_payment_ledger":
            return {"ok": True, "gl_entries": []}
        if tool == "get_remittance_delivery":
            return {"ok": True, "delivered": self.delivered, "delivery": None}
        if tool == "find_remittance_jobs":
            return {"ok": True, "jobs": self.jobs}
        if tool in {
            "submit_payment_entry",
            "requeue_payment_remittance",
            "resume_remittance_workers",
        }:
            return {"ok": True}
        if tool == "wait_for_remittance_delivery":
            return {"ok": True, "delivered": True}
        raise AssertionError(tool)


class ERPNextReferenceRecoveryTest(unittest.TestCase):
    def _mutations(self, fixture):
        reference_erpnext_recovery(fixture)
        return [
            tool
            for tool, _arguments in fixture.calls
            if tool
            in {
                "submit_payment_entry",
                "requeue_payment_remittance",
                "resume_remittance_workers",
            }
        ]

    def test_draft_payment_is_submitted(self) -> None:
        fixture = _ReferenceFixture(docstatus=0, delivered=False, jobs=[])
        self.assertEqual(self._mutations(fixture), ["submit_payment_entry"])

    def test_completed_remittance_requires_no_mutation(self) -> None:
        fixture = _ReferenceFixture(docstatus=1, delivered=True, jobs=[])
        self.assertEqual(self._mutations(fixture), [])
        self.assertNotIn(
            "wait_for_remittance_delivery",
            [tool for tool, _arguments in fixture.calls],
        )

    def test_missing_job_is_requeued(self) -> None:
        fixture = _ReferenceFixture(docstatus=1, delivered=False, jobs=[])
        self.assertEqual(
            self._mutations(fixture),
            ["requeue_payment_remittance"],
        )

    def test_existing_job_resumes_workers_without_requeue(self) -> None:
        fixture = _ReferenceFixture(
            docstatus=1,
            delivered=False,
            jobs=[{"name": "job-1", "status": "queued"}],
        )
        self.assertEqual(
            self._mutations(fixture),
            ["resume_remittance_workers"],
        )

    @patch("aftermath_bench.integrations.erpnext_agent.time.sleep")
    def test_wait_requires_delivery_and_job_settlement(self, sleep) -> None:
        adapter = Mock()
        adapter.list_resources.side_effect = [
            {
                "data": [
                    {
                        "name": "job-1",
                        "status": "started",
                        "arguments": '{"payment_entry":"PAY-1"}',
                    }
                ]
            },
            {
                "data": [
                    {
                        "name": "job-1",
                        "status": "finished",
                        "arguments": '{"payment_entry":"PAY-1"}',
                    }
                ]
            },
        ]
        collector = Mock()
        collector.get_remittance_delivery.return_value = {
            "key": "PAY-1",
            "attempt_count": 1,
        }
        environment = ERPNextRecoveryEnvironment(
            adapter=adapter,
            ids=ProcurementPaymentIDs("PO-1", "PR-1", "PI-1"),
            payment_entry="PAY-1",
            stack=Mock(),
            worker_control=Mock(),
            collector=collector,
        )

        result = environment._wait_for_remittance("PAY-1", 10)

        self.assertTrue(result["delivered"])
        self.assertTrue(result["jobs_settled"])
        self.assertEqual(result["relevant_jobs"][0]["status"], "finished")
        sleep.assert_called_once_with(0.25)


if __name__ == "__main__":
    unittest.main()
