from __future__ import annotations

import unittest

from scripts.build_native_sales_return_admission import (
    _build_graph,
    _minimum_distinguishing_signal_count,
)


class NativeSalesAdmissionBuilderTest(unittest.TestCase):
    def test_final_graph_uses_durable_delivery_not_ephemeral_finished_job(
        self,
    ) -> None:
        prefix = {
            "scenario_id": "erpnext-sales-return-test",
            "original_sales_order": "SO-1",
            "original_delivery_note": "DN-1",
            "quality_inspection": "QI-1",
            "affected_invoice": "SI-1",
            "unaffected_invoice": "SI-2",
            "shared_payment_entry": "PE-1",
            "sales_return": "DN-RET-1",
            "credit_note": "SI-CN-1",
            "replacement_sales_order": "SO-2",
            "replacement_delivery_note": "DN-2",
            "affected_item": "ITEM-A",
            "unaffected_item": "ITEM-B",
            "replacement_item": "ITEM-C",
            "customer": "CUSTOMER-1",
        }
        references = [
            {
                "final_evidence": {
                    "replacement_invoices": [{"name": "SI-3"}],
                    "rq_jobs": [],
                    "pickup_delivery": {
                        "key": "DN-RET-1",
                        "attempt_count": 1,
                    },
                }
            }
        ]
        failures = [
            {
                "variant": variant,
                "failure_boundary_evidence": {
                    "sales_return": {"docstatus": docstatus},
                    "pickup_delivery": delivery,
                    "rq_jobs": jobs,
                },
            }
            for variant, docstatus, delivery, jobs in (
                ("request_not_reached", 0, None, []),
                (
                    "database_committed_response_lost",
                    1,
                    {"key": "DN-RET-1"},
                    [],
                ),
                ("after_commit_enqueue_failed", 1, None, []),
                (
                    "async_job_pending",
                    1,
                    None,
                    [
                        {
                            "name": "job-1",
                            "status": "queued",
                            "arguments": "DN-RET-1",
                        }
                    ],
                ),
            )
        ]

        graph = _build_graph(prefix, references, failures)

        entity_ids = {entity["id"] for entity in graph["entities"]}
        self.assertNotIn("pickup_job", entity_ids)
        delivery_relations = [
            relation
            for relation in graph["relations"]
            if relation["target"] == "pickup_delivery"
        ]
        self.assertEqual(len(delivery_relations), 1)
        self.assertEqual(delivery_relations[0]["source"], "sales_return")
        self.assertEqual(
            delivery_relations[0]["type"],
            "triggers_external_delivery",
        )
        self.assertNotIn("rq_jobs", delivery_relations[0]["evidence"])

    def test_all_three_authoritative_signals_are_required(self) -> None:
        rows = [
            {
                "signals": {
                    "sales_return": 0,
                    "external_delivery": False,
                    "background_job": False,
                }
            },
            {
                "signals": {
                    "sales_return": 1,
                    "external_delivery": True,
                    "background_job": False,
                }
            },
            {
                "signals": {
                    "sales_return": 1,
                    "external_delivery": False,
                    "background_job": False,
                }
            },
            {
                "signals": {
                    "sales_return": 1,
                    "external_delivery": False,
                    "background_job": True,
                }
            },
        ]
        self.assertEqual(
            _minimum_distinguishing_signal_count(
                rows,
                (
                    "sales_return",
                    "external_delivery",
                    "background_job",
                ),
            ),
            3,
        )


if __name__ == "__main__":
    unittest.main()
