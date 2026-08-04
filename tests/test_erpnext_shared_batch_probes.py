from __future__ import annotations

import unittest
from unittest.mock import patch

from aftermath_bench.integrations.erpnext_shared_batch_probes import (
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


if __name__ == "__main__":
    unittest.main()
