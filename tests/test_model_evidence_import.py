from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.model_evidence_import import (
    ModelEvidenceImportError,
    ModelEvidenceImportGate,
    validate_model_artifact,
    validate_source_provenance,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ModelEvidenceImportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.stage = self.root / "stage"
        self.stage.mkdir()
        scenario = {
            "scenario_id": "public-hard-dev-001",
            "benchmark_split": "public_dev",
            "matched_variants": [
                {"id": "state_01"},
                {"id": "state_02"},
            ],
        }
        self.scenario_path = self.root / "data" / "scenarios" / "public" / "scenario.json"
        self.scenario_path.parent.mkdir(parents=True)
        self.scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
        repetition = self.stage / "model-runs" / "repetition-01"
        repetition.mkdir(parents=True)
        reports = []
        for index, variant in enumerate(("state_01", "state_02"), start=1):
            passed = index == 1
            trajectory = {
                "run_id": f"run-{index}",
                "scenario_id": "public-hard-dev-001",
                "variant": variant,
                "provider": "openai-compatible",
                "model": "strong-model",
                "execution_control": False,
                "evaluation": {
                    "passed": passed,
                    "components": {
                        "goal_completion": True,
                        "repair_completeness": passed,
                        "preservation": True,
                        "protocol_safety": True,
                    },
                },
                "trajectory_diagnostics": {
                    "primary_error": None if passed else "scope_failure"
                },
            }
            (repetition / f"{variant}.json").write_text(
                json.dumps(trajectory), encoding="utf-8"
            )
            reports.append(
                {
                    "scenario_id": "public-hard-dev-001",
                    "variant": variant,
                    "passed": passed,
                }
            )
        summary = {
            "completed_runs": 2,
            "run_errors": [],
            "execution_control_counts": {"false": 2},
            "matched_group_success_rate": 0.0,
            "reports": reports,
        }
        (self.stage / "model-runs" / "summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
        self.gate_value = {
            "schema_version": "1.0",
            "stage": "ordinary-model-evidence-import",
            "sources": [
                {
                    "evidence_id": "run-123-ordinary",
                    "source_run_id": 123,
                    "source_commit": "a" * 40,
                    "source_workflow": ".github/workflows/model.yml",
                    "artifact_id": 456,
                    "artifact_name": "public-model-123",
                    "artifact_digest": "sha256:" + "b" * 64,
                    "artifact_size_in_bytes": 1000,
                    "scenario_id": "public-hard-dev-001",
                    "scenario_path": "data/scenarios/public/scenario.json",
                    "scenario_sha256": _sha256(self.scenario_path),
                    "expected_variant_ids": ["state_01", "state_02"],
                    "conditions": [
                        {
                            "condition_id": "strong-model",
                            "model": "strong-model",
                            "provider": "openai-compatible",
                            "provider_service": "test-provider",
                            "repetition": 1,
                            "summary_path": "model-runs/summary.json",
                            "trajectory_root": "model-runs",
                            "accounting_status": "ordinary-model-tested",
                        }
                    ],
                }
            ],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _source(self):
        return ModelEvidenceImportGate.from_mapping(self.gate_value).sources[0]

    def test_validates_complete_ordinary_artifact(self) -> None:
        report = validate_model_artifact(
            self.stage, source=self._source(), root=self.root
        )

        self.assertTrue(report["infrastructure_valid"])
        condition = report["conditions"][0]
        self.assertEqual(condition["task_pass_count"], 1)
        self.assertFalse(condition["matched_group_success"])
        self.assertEqual(condition["failure_type_counts"], {"scope_failure": 1})
        self.assertEqual(len(condition["trajectories"]), 2)

    def test_rejects_execution_control_as_ordinary(self) -> None:
        path = self.stage / "model-runs" / "repetition-01" / "state_01.json"
        trajectory = json.loads(path.read_text(encoding="utf-8"))
        trajectory["execution_control"] = True
        path.write_text(json.dumps(trajectory), encoding="utf-8")

        with self.assertRaisesRegex(
            ModelEvidenceImportError, "identity failed: ordinary"
        ):
            validate_model_artifact(
                self.stage, source=self._source(), root=self.root
            )

    def test_rejects_changed_scenario_identity(self) -> None:
        self.scenario_path.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(
            ModelEvidenceImportError, "scenario hash differs"
        ):
            validate_model_artifact(
                self.stage, source=self._source(), root=self.root
            )

    def test_rejects_duplicate_source_runs(self) -> None:
        duplicate = dict(self.gate_value["sources"][0])
        duplicate["evidence_id"] = "run-123-duplicate"
        self.gate_value["sources"].append(duplicate)

        with self.assertRaisesRegex(ModelEvidenceImportError, "source_run_id"):
            ModelEvidenceImportGate.from_mapping(self.gate_value)

    def test_validates_source_run_and_artifact_digest(self) -> None:
        source = self._source()
        provenance = validate_source_provenance(
            {
                "id": 123,
                "head_sha": "a" * 40,
                "status": "completed",
                "conclusion": "success",
                "path": ".github/workflows/model.yml",
            },
            {
                "artifacts": [
                    {
                        "id": 456,
                        "name": "public-model-123",
                        "digest": "sha256:" + "b" * 64,
                        "size_in_bytes": 1000,
                        "expired": False,
                    }
                ]
            },
            source=source,
        )

        self.assertTrue(all(provenance["checks"].values()))


if __name__ == "__main__":
    unittest.main()
