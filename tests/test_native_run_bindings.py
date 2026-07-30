from __future__ import annotations

import unittest
from pathlib import Path

from aftermath_bench.native_model_runner import (
    validate_native_run_bindings,
)
from aftermath_bench.native_scenario import NativeScenario


class NativeRunBindingTests(unittest.TestCase):
    def _scenario(self) -> NativeScenario:
        return NativeScenario(
            path=Path("scenario.json"),
            raw={
                "scenario_id": "publication-hidden-001",
                "instance_spec_sha256": "spec-a",
                "matched_variants": [{"id": "opaque-01"}],
            },
        )

    def test_accepts_matching_bound_inputs(self) -> None:
        validate_native_run_bindings(
            scenario=self._scenario(),
            prefix={
                "scenario_id": "publication-hidden-001",
                "instance_spec_sha256": "spec-a",
            },
            failure_report={
                "scenario_id": "publication-hidden-001",
                "instance_spec_sha256": "spec-a",
                "variant": "opaque-01",
            },
            family_id="forgejo-release-package-publication",
        )

    def test_rejects_cross_wired_prefix(self) -> None:
        with self.assertRaisesRegex(ValueError, "prefix and scenario"):
            validate_native_run_bindings(
                scenario=self._scenario(),
                prefix={
                    "scenario_id": "other",
                    "instance_spec_sha256": "spec-a",
                },
                failure_report={
                    "scenario_id": "publication-hidden-001",
                    "instance_spec_sha256": "spec-a",
                    "variant": "opaque-01",
                },
                family_id="forgejo-release-package-publication",
            )

    def test_rejects_unknown_variant_and_spec_hash_drift(self) -> None:
        with self.assertRaisesRegex(ValueError, "variant"):
            validate_native_run_bindings(
                scenario=self._scenario(),
                prefix={
                    "scenario_id": "publication-hidden-001",
                    "instance_spec_sha256": "spec-a",
                },
                failure_report={
                    "scenario_id": "publication-hidden-001",
                    "instance_spec_sha256": "spec-a",
                    "variant": "not-declared",
                },
                family_id="forgejo-release-package-publication",
            )
        with self.assertRaisesRegex(ValueError, "instance specs"):
            validate_native_run_bindings(
                scenario=self._scenario(),
                prefix={
                    "scenario_id": "publication-hidden-001",
                    "instance_spec_sha256": "spec-b",
                },
                failure_report={
                    "scenario_id": "publication-hidden-001",
                    "instance_spec_sha256": "spec-a",
                    "variant": "opaque-01",
                },
                family_id="forgejo-release-package-publication",
            )


if __name__ == "__main__":
    unittest.main()
