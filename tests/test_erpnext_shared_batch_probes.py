from __future__ import annotations

import unittest
from unittest.mock import patch

from aftermath_bench.integrations.erpnext_shared_batch_probes import (
    SHARED_BATCH_INTERACTION_PROBES,
    run_shared_batch_interaction_probe,
)


class _Environment:
    def __init__(self) -> None:
        self.calls = []

    def invoke(self, tool: str, **arguments):
        self.calls.append((tool, arguments))
        return {"ok": True, "document": {"docstatus": 2}}


class SharedBatchProbeTests(unittest.TestCase):
    @patch(
        "aftermath_bench.integrations.erpnext_shared_batch_probes."
        "reference_shared_batch_recovery",
        return_value=({"tool": "get_document", "arguments": {}, "result": {}},),
    )
    def test_probe_repairs_then_cancels_only_the_shared_reservation(self, reference):
        environment = _Environment()
        trace = run_shared_batch_interaction_probe(
            environment,
            prefix={"stock_reservation_entry": "SRE-CROSS-001"},
        )
        reference.assert_called_once_with(environment)
        self.assertEqual(
            environment.calls,
            [
                (
                    "cancel_document",
                    {
                        "doctype": "Stock Reservation Entry",
                        "name": "SRE-CROSS-001",
                    },
                )
            ],
        )
        self.assertEqual(trace[-1]["tool"], "cancel_document")

    @patch(
        "aftermath_bench.integrations.erpnext_shared_batch_probes."
        "reference_shared_batch_recovery",
        return_value=(),
    )
    def test_each_probe_cancels_a_distinct_native_document(self, _reference):
        expected = {
            "repair_then_cancel_customer_reservation": (
                "Stock Reservation Entry",
                "SRE-CROSS-001",
            ),
            "repair_then_cancel_accepted_quality_inspection": (
                "Quality Inspection",
                "QI-CROSS-001",
            ),
            "repair_then_cancel_unrelated_receipt": (
                "Stock Entry",
                "STE-CROSS-001",
            ),
        }
        prefix = {
            "stock_reservation_entry": "SRE-CROSS-001",
            "accepted_primary_quality_inspection": "QI-CROSS-001",
            "unrelated_receipt": "STE-CROSS-001",
        }
        for probe in SHARED_BATCH_INTERACTION_PROBES:
            with self.subTest(probe=probe):
                environment = _Environment()
                run_shared_batch_interaction_probe(
                    environment, prefix=prefix, probe=probe
                )
                doctype, name = expected[probe]
                self.assertEqual(
                    environment.calls,
                    [
                        (
                            "cancel_document",
                            {"doctype": doctype, "name": name},
                        )
                    ],
                )


if __name__ == "__main__":
    unittest.main()
