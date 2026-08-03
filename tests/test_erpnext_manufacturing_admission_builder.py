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
from scripts.build_erpnext_manufacturing_admission import (
    VARIANT_DIRECTIONS,
    build_admission,
    _build_graph,
    _normalise_evidence,
)


class ERPNextManufacturingAdmissionBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.prefix = {
            "scenario_id": "erpnext-manufacturing-rework-dev-001",
            "finished_item": "FG",
            "raw_items": ["RAW-A", "RAW-B"],
            "bom": "BOM-1",
            "work_order": "WO-1",
            "accepted_job_card": "JC-A",
            "rejected_job_card": "JC-R",
            "corrective_job_card": "JC-C",
            "accepted_quality_inspection": "QI-A",
            "rejected_quality_inspection": "QI-R",
            "material_transfer_stock_entry": "SE-T",
            "accepted_manufacture_stock_entry": "SE-A",
            "unrelated_stock_entry": "SE-U",
            "corrective_operation": "OP-C",
            "quality_release_webhook": "HOOK-C",
        }
        self.evidence = {
            "bom": {
                "name": "BOM-1",
                "item": "FG",
                "items": [{"item_code": "RAW-A"}, {"item_code": "RAW-B"}],
            },
            "work_order": {"name": "WO-1", "bom_no": "BOM-1"},
            "accepted_job_card": {"name": "JC-A", "work_order": "WO-1"},
            "rejected_job_card": {"name": "JC-R", "work_order": "WO-1"},
            "corrective_job_card": {
                "name": "JC-C",
                "work_order": "WO-1",
                "for_job_card": "JC-R",
                "operation": "OP-C",
                "docstatus": 1,
            },
            "accepted_quality_inspection": {
                "name": "QI-A",
                "reference_name": "SE-A",
            },
            "rejected_quality_inspection": {
                "name": "QI-R",
                "reference_name": "JC-R",
            },
            "material_transfer_stock_entry": {
                "name": "SE-T",
                "work_order": "WO-1",
                "docstatus": 1,
            },
            "accepted_manufacture_stock_entry": {
                "name": "SE-A",
                "work_order": "WO-1",
                "bom_no": "BOM-1",
                "docstatus": 1,
            },
            "unrelated_stock_entry": {
                "name": "SE-U",
                "docstatus": 1,
                "items": [{"item_code": "UNRELATED"}],
            },
            "manufacture_stock_entries": [
                {
                    "name": "SE-A",
                    "purpose": "Manufacture",
                    "work_order": "WO-1",
                    "bom_no": "BOM-1",
                    "docstatus": 1,
                },
                {
                    "name": "SE-F",
                    "purpose": "Manufacture",
                    "work_order": "WO-1",
                    "bom_no": "BOM-1",
                    "docstatus": 1,
                },
            ],
            "quality_inspections": [
                {"name": "QI-M1", "reference_name": "SE-T"},
                {"name": "QI-M2", "reference_name": "SE-T"},
                {
                    "name": "QI-F",
                    "reference_type": "Stock Entry",
                    "reference_name": "SE-F",
                    "docstatus": 1,
                },
            ],
            "stock_ledger_entries": [
                {"voucher_no": voucher}
                for voucher in ("SE-T", "SE-A", "SE-F", "SE-U")
            ],
            "gl_entries": [
                {"voucher_no": voucher} for voucher in ("SE-A", "SE-F")
            ],
            "rq_jobs": [],
            "quality_release_delivery": {"key": "JC-C", "attempt_count": 1},
        }

    def test_every_declared_relation_replays_on_all_variants(self) -> None:
        references = [
            {"variant": variant, "final_evidence": copy.deepcopy(self.evidence)}
            for variant in VARIANT_DIRECTIONS
        ]
        failures = []
        for index, variant in enumerate(VARIANT_DIRECTIONS):
            boundary = copy.deepcopy(self.evidence)
            boundary["corrective_job_card"]["docstatus"] = 0 if index == 0 else 1
            boundary["quality_release_delivery"] = (
                self.evidence["quality_release_delivery"] if index == 1 else None
            )
            boundary["rq_jobs"] = (
                [{"status": "queued"}] if index == 3 else []
            )
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

    def test_hidden_split_must_match_hidden_eligibility(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "prefix.json").write_text(
                json.dumps({"scenario_id": "hidden-001"}), encoding="utf-8"
            )
            blueprint = root / "blueprint.json"
            blueprint.write_text(
                json.dumps(
                    {
                        "scenario_id": "hidden-001",
                        "benchmark_split": "hidden_test",
                        "hidden_test_eligible": False,
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "scripts.build_erpnext_manufacturing_admission._load_inputs"
            ):
                with self.assertRaisesRegex(RuntimeError, "eligibility"):
                    build_admission(
                        runtime_directory=runtime,
                        blueprint_path=blueprint,
                        output_directory=root / "output",
                    )


if __name__ == "__main__":
    unittest.main()
