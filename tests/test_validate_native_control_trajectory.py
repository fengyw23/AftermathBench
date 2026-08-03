from __future__ import annotations

import unittest

from aftermath_bench.erpnext_manufacturing_state_evidence import (
    manufacturing_boundary_projection,
)
from aftermath_bench.erpnext_sales_return_state_evidence import (
    canonical_state_fingerprint,
)
from scripts.validate_native_control_trajectory import (
    validate_control_trajectory,
)


VARIANT = "release_request_not_reached"


def _trajectory(*, passed: bool) -> dict:
    boundary_sha256 = "b" * 64
    return {
        "run_id": "run-001",
        "scenario_id": "scenario-001",
        "instance_spec_sha256": "a" * 64,
        "variant": VARIANT,
        "execution_control": True,
        "surface_failure": {"error": "connection lost"},
        "turns": [{"turn": 1, "tool_calls": []}],
        "final_evidence": {},
        "evaluation": {"passed": passed},
        "formal_input_lock": {
            "variant_id": VARIANT,
            "lock_sha256": "c" * 64,
            "boundary_state_sha256": boundary_sha256,
            "failure_report_sha256": "d" * 64,
            "prefix_sha256": "e" * 64,
        },
        "pre_model_boundary_evidence": {
            "variant_id": VARIANT,
            "source_basename": f"{VARIANT}-boundary.json",
            "sha256": boundary_sha256,
        },
    }


class ValidateNativeControlTrajectoryTest(unittest.TestCase):
    def test_accepts_complete_model_failure_without_retrying_it(self) -> None:
        self.assertEqual(
            validate_control_trajectory(
                _trajectory(passed=False),
                variant=VARIANT,
            ),
            (),
        )

    def test_rejects_empty_or_wrongly_bound_trajectory(self) -> None:
        self.assertIn(
            "variant_mismatch",
            validate_control_trajectory({}, variant=VARIANT),
        )
        payload = _trajectory(passed=True)
        payload["pre_model_boundary_evidence"]["sha256"] = "f" * 64

        failures = validate_control_trajectory(payload, variant=VARIANT)

        self.assertIn("pre_model_boundary_lock_mismatch", failures)

    def test_rejects_missing_formal_fields_but_not_failed_evaluation(self) -> None:
        payload = _trajectory(passed=False)
        payload.pop("formal_input_lock")

        failures = validate_control_trajectory(payload, variant=VARIANT)

        self.assertEqual(failures, ("missing_formal_input_lock",))

    def test_accepts_only_trusted_semantic_boundary_equivalence(self) -> None:
        payload = _trajectory(passed=True)
        payload["family"] = "erpnext-manufacturing-rework"
        payload["pre_model_boundary_evidence"]["sha256"] = "f" * 64
        locked = self._manufacturing_capture({"rq_jobs": []})
        live = self._manufacturing_capture(
            {"rq_jobs": [{"name": "job-1", "status": "finished"}]}
        )

        self.assertEqual(
            validate_control_trajectory(
                payload,
                variant=VARIANT,
                locked_boundary=locked,
                pre_model_boundary=live,
            ),
            (),
        )
        live = self._manufacturing_capture(
            {"rq_jobs": [{"name": "job-1", "status": "queued"}]}
        )
        self.assertIn(
            "pre_model_boundary_lock_mismatch",
            validate_control_trajectory(
                payload,
                variant=VARIANT,
                locked_boundary=locked,
                pre_model_boundary=live,
            ),
        )

    @staticmethod
    def _manufacturing_capture(state: dict) -> dict:
        return {
            "schema_version": "1.0",
            "artifact_type": "erpnext_manufacturing_state_evidence",
            "scenario_id": "manufacturing-1",
            "instance_id": "dev-001",
            "variant_id": VARIANT,
            "phase": "boundary",
            "failure_report_file_sha256": "1" * 64,
            "state_fingerprint": canonical_state_fingerprint(state),
            "failure_state_semantic_fingerprint": canonical_state_fingerprint(
                manufacturing_boundary_projection(state)
            ),
            "state": state,
        }


if __name__ == "__main__":
    unittest.main()
