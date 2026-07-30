from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.native_scenario import (
    NativeScenario,
    load_native_scenario,
    native_scenario_paths,
    validate_native_scenario_document,
)
from aftermath_bench.strict_json import loads_strict


class NativeScenarioSchemaTest(unittest.TestCase):
    def test_active_scenarios_have_canonical_identity(self) -> None:
        for path in native_scenario_paths():
            with self.subTest(path=path):
                scenario = load_native_scenario(path)
                self.assertFalse(
                    validate_native_scenario_document(scenario),
                    validate_native_scenario_document(scenario),
                )

    def test_artifact_cannot_escape_scenario_directory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = NativeScenario(
                path=root / "scenario.json",
                raw={
                    "schema_version": "1.0",
                    "scenario_id": "escape-test",
                    "domain_id": "erpnext",
                    "instance_id": "dev-001",
                    "family": "example-family",
                    "runtime_id": "erpnext-v15",
                    "benchmark_split": "development",
                    "benchmark_tier": "easy",
                    "title": "Escape test",
                    "user_instruction": "Test path containment.",
                    "ambiguous_operation": {
                        "operation": "write",
                        "surface_result": "error",
                    },
                    "matched_variants": [{"id": "state-1"}],
                    "admission_artifacts": {
                        "prefix": "../outside.json",
                        "reference": "artifacts/reference.json",
                        "observed_graph": "artifacts/graph.json",
                        "baselines": "artifacts/baselines.json",
                    },
                },
            )
            with self.assertRaises(ValueError):
                scenario.resolve_artifact("prefix")
            self.assertIn(
                "unsafe_admission_artifact:prefix",
                validate_native_scenario_document(scenario),
            )

    def test_artifact_rejects_windows_and_absolute_paths(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            base = {
                "schema_version": "1.0",
                "admission_artifacts": {"prefix": "artifacts/prefix.json"},
            }
            scenario = NativeScenario(path=root / "scenario.json", raw=base)
            for value in (
                r"artifacts\prefix.json",
                "/artifacts/prefix.json",
                "C:/artifacts/prefix.json",
            ):
                with self.subTest(value=value):
                    base["admission_artifacts"]["prefix"] = value
                    with self.assertRaises(ValueError):
                        scenario.resolve_artifact("prefix")

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            loads_strict('{"scenario_id":"a","scenario_id":"b"}')
        with self.assertRaisesRegex(ValueError, "non-finite"):
            loads_strict('{"value":NaN}')


if __name__ == "__main__":
    unittest.main()
