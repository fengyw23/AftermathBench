from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.analyze_erpnext_sales_return_runs import (
    analyze_sales_return_runs,
)


def _report(
    *,
    variant: str,
    passed: bool,
    linked_query: bool,
) -> dict:
    return {
        "family": "erpnext-sales-return-exchange-reconciliation",
        "variant": variant,
        "execution_control": False,
        "stop_reason": "model_stopped",
        "turns": [{"tool_calls": [{}, {}]}],
        "evaluation": {
            "passed": passed,
            "components": {
                "goal_completion": True,
                "repair_completeness": True,
                "preservation": True,
                "protocol_safety": passed,
            },
            "checks": {
                "no_duplicate_replacement_invoice": passed,
            },
        },
        "trajectory_diagnostics": {
            "primary_error": None if passed else "investigation_failure",
            "selected_mutations": ["submit_document"],
            "queried_linked_invoices_before_create": linked_query,
            "created_invoice_without_linked_invoice_investigation": (
                not linked_query
            ),
            "unsafe_return_resubmit": False,
            "tool_error_count": 0,
        },
    }


class ERPNextSalesReturnAnalysisTest(unittest.TestCase):
    def test_aggregates_scope_investigation_failure(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.json").write_text(
                json.dumps(
                    _report(
                        variant="request_not_reached",
                        passed=True,
                        linked_query=True,
                    )
                ),
                encoding="utf-8",
            )
            (root / "b.json").write_text(
                json.dumps(
                    _report(
                        variant="database_committed_response_lost",
                        passed=False,
                        linked_query=False,
                    )
                ),
                encoding="utf-8",
            )
            result = analyze_sales_return_runs(root)

        self.assertEqual(result["completed_runs"], 2)
        self.assertEqual(result["task_pass_rate"], 0.5)
        self.assertEqual(
            result["primary_error_counts"],
            {"investigation_failure": 1},
        )
        self.assertEqual(result["linked_invoice_investigation_rate"], 0.5)
        self.assertEqual(
            result["created_without_invoice_investigation_count"],
            1,
        )
        self.assertEqual(result["tool_error_count"], 0)

    def test_refines_stale_post_mutation_plan_from_raw_trajectory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / "model-runs"
            runs.mkdir()
            (root / "prefix.json").write_text(
                json.dumps(
                    {
                        "replacement_sales_order": "SO-REPLACEMENT",
                        "replacement_delivery_note": "DN-REPLACEMENT",
                    }
                ),
                encoding="utf-8",
            )
            report = _report(
                variant="request_not_reached",
                passed=False,
                linked_query=False,
            )
            report["trajectory_diagnostics"].update(
                {
                    "primary_error": "scope_failure",
                    "created_invoice_without_linked_invoice_investigation": (
                        False
                    ),
                }
            )
            report["turns"] = [
                {
                    "tool_calls": [
                        {
                            "name": "submit_document",
                            "arguments": {
                                "doctype": "Delivery Note",
                                "name": "DN-REPLACEMENT",
                            },
                        },
                        {
                            "name": "create_sales_invoice_from_order",
                            "arguments": {
                                "sales_order": "SO-REPLACEMENT",
                            },
                        },
                    ]
                }
            ]
            (runs / "trajectory.json").write_text(
                json.dumps(report),
                encoding="utf-8",
            )

            result = analyze_sales_return_runs(runs)

        self.assertEqual(
            result["reported_primary_error_counts"],
            {"scope_failure": 1},
        )
        self.assertEqual(
            result["primary_error_counts"],
            {"investigation_failure": 1},
        )
        self.assertEqual(
            result["failure_subtype_counts"],
            {"post_mutation_state_not_refreshed": 1},
        )
        self.assertEqual(
            result[
                "created_after_delivery_without_state_refresh_count"
            ],
            1,
        )


if __name__ == "__main__":
    unittest.main()
