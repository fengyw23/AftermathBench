from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aftermath_bench.evidence_replay import (
    project_evidence,
    replay_graph,
    replay_selectors,
)
from scripts.build_erpnext_multiwarehouse_admission import (
    VARIANT_DIRECTIONS,
    build_admission,
    _build_graph,
    _normalise_evidence,
)


class ERPNextMultiwarehouseAdmissionBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prefix = {
            "scenario_id": "erpnext-multiwarehouse-transfer-dev-001",
            "transfer_item": "GATEWAY",
            "protected_item": "ROUTER",
            "batch_id": "BATCH-G",
            "source_warehouse": "East - AL",
            "transit_warehouse": "Transit - AL",
            "destination_warehouse": "West - AL",
            "protected_warehouse": "North - AL",
            "stock_seed": "SE-SEED",
            "material_request": "MR-1",
            "outgoing_stock_entry": "SE-OUT",
            "second_leg_stock_entry": "SE-IN",
            "clinic_sales_order": "SO-C",
            "protected_sales_order": "SO-P",
            "protected_pick_list": "PL-P",
            "protected_reservation": "SRE-P",
            "arrival_webhook": "WH-ARRIVAL",
        }
        self.evidence = {
            "stock_seed": {"name": "SE-SEED", "items": [{"item_code": "ROUTER"}]},
            "material_request": {"name": "MR-1", "items": [{"item_code": "GATEWAY"}]},
            "outgoing_stock_entry": {
                "name": "SE-OUT",
                "items": [
                    {
                        "item_code": "GATEWAY",
                        "material_request": "MR-1",
                        "batch_no": "BATCH-G",
                        "s_warehouse": "East - AL",
                    }
                ],
            },
            "second_leg_stock_entries": [
                {
                    "name": "SE-IN",
                    "docstatus": 1,
                    "outgoing_stock_entry": "SE-OUT",
                    "items": [
                        {
                            "item_code": "GATEWAY",
                            "s_warehouse": "Transit - AL",
                            "t_warehouse": "West - AL",
                        }
                    ],
                }
            ],
            "clinic_sales_order": {"name": "SO-C", "items": [{"item_code": "GATEWAY"}]},
            "clinic_pick_lists": [
                {
                    "name": "PL-C",
                    "docstatus": 1,
                    "locations": [
                        {"sales_order": "SO-C", "warehouse": "West - AL"}
                    ],
                }
            ],
            "protected_sales_order": {"name": "SO-P", "items": [{"item_code": "ROUTER"}]},
            "protected_pick_list": {
                "name": "PL-P",
                "locations": [{"sales_order": "SO-P", "warehouse": "North - AL"}],
            },
            "protected_reservation": {
                "name": "SRE-P",
                "item_code": "ROUTER",
                "voucher_no": "SO-P",
            },
            "stock_reservation_entries": [
                {"name": "SRE-C", "docstatus": 1, "item_code": "GATEWAY", "voucher_no": "SO-C"},
                {"name": "SRE-P", "docstatus": 1, "item_code": "ROUTER", "voucher_no": "SO-P"},
            ],
            "stock_ledger_entries": [
                {"name": "SLE-T", "voucher_no": "SE-IN", "item_code": "GATEWAY", "warehouse": "Transit - AL"},
                {"name": "SLE-D", "voucher_no": "SE-IN", "item_code": "GATEWAY", "warehouse": "West - AL"},
            ],
            "bins": [
                {"name": "BIN-T", "item_code": "GATEWAY", "warehouse": "Transit - AL"},
                {"name": "BIN-D", "item_code": "GATEWAY", "warehouse": "West - AL"},
                {"name": "BIN-P", "item_code": "ROUTER", "warehouse": "North - AL"},
            ],
            "arrival_deliveries": {"SE-IN": {"key": "SE-IN", "attempt_count": 1}},
            "rq_jobs": [],
        }

    def test_graph_is_replayable_and_meets_structural_floor(self) -> None:
        references = [
            {"variant": variant, "final_evidence": copy.deepcopy(self.evidence)}
            for variant in VARIANT_DIRECTIONS
        ]
        failures = []
        for index, variant in enumerate(VARIANT_DIRECTIONS):
            boundary = copy.deepcopy(self.evidence)
            boundary["second_leg_stock_entries"][0]["docstatus"] = 0 if index == 0 else 1
            boundary["arrival_deliveries"] = (
                self.evidence["arrival_deliveries"] if index == 1 else {}
            )
            boundary["rq_jobs"] = [{"status": "queued"}] if index == 3 else []
            failures.append({"variant": variant, "boundary_evidence": boundary})
        graph = _build_graph(self.prefix, references, failures)
        selectors = replay_selectors(graph)
        replay = {
            "captures": [
                {
                    "variant": report["variant"],
                    "evidence": project_evidence(
                        _normalise_evidence(report["final_evidence"], self.prefix),
                        selectors,
                    ),
                }
                for report in references
            ]
        }
        results = replay_graph(graph, replay)
        self.assertTrue(results)
        self.assertTrue(all(result.passed for result in results), results)
        self.assertGreaterEqual(len(graph["entities"]), 20)
        self.assertGreaterEqual(len({row["type"] for row in graph["relations"]}), 8)

    def test_public_split_cannot_claim_hidden_eligibility(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "prefix.json").write_text(
                json.dumps({"scenario_id": "public-001"}), encoding="utf-8"
            )
            blueprint = root / "blueprint.json"
            blueprint.write_text(
                json.dumps(
                    {
                        "scenario_id": "public-001",
                        "benchmark_split": "public_dev",
                        "hidden_test_eligible": True,
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "scripts.build_erpnext_multiwarehouse_admission._load_inputs"
            ):
                with self.assertRaisesRegex(RuntimeError, "eligibility"):
                    build_admission(
                        runtime_directory=runtime,
                        blueprint_path=blueprint,
                        output_directory=root / "output",
                    )


if __name__ == "__main__":
    unittest.main()
