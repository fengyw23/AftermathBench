import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.core import canonical_fingerprint
from aftermath_bench.scenarios.itsm_major_incident import (
    ITSM_VARIANTS,
    build_itsm_failure_state,
    evaluate_itsm,
    reference_itsm_recovery,
    verify_itsm_sql,
)


class ITSMMajorIncidentTest(unittest.TestCase):
    def test_all_matched_variants_recover(self) -> None:
        for variant in ITSM_VARIANTS:
            with self.subTest(variant=variant):
                environment, proxy, failure = build_itsm_failure_state(variant)
                try:
                    self.assertEqual(
                        failure,
                        {"ok": False, "error": "504 Gateway Timeout"},
                    )
                    reference_itsm_recovery(environment)
                    self.assertTrue(evaluate_itsm(environment)["passed"])
                    self.assertTrue(verify_itsm_sql(environment)["passed"])
                    self.assertEqual(len(proxy.events), 1)
                finally:
                    environment.close()

    def test_incident_only_view_misses_partial_commit_residue(self) -> None:
        environment, _proxy, _failure = build_itsm_failure_state("partial_commit")
        try:
            incident = environment.invoke(
                "find_incident",
                incident_id=environment.INCIDENT_ID,
            )["data"]
            self.assertEqual(incident["priority"], 1)
            result = evaluate_itsm(environment)
            self.assertFalse(result["goal_completion"])
            self.assertFalse(result["integrity"])
        finally:
            environment.close()

    def test_blind_retry_is_unsafe_after_response_loss(self) -> None:
        environment, _proxy, _failure = build_itsm_failure_state(
            "commit_response_lost"
        )
        try:
            environment.invoke(
                "escalate_major_incident",
                incident_id=environment.INCIDENT_ID,
            )
            self.assertFalse(evaluate_itsm(environment)["protocol_safety"])
        finally:
            environment.close()

    def test_failure_checkpoint_round_trip_is_identical(self) -> None:
        environment, _proxy, _failure = build_itsm_failure_state("async_pending")
        try:
            with TemporaryDirectory() as directory:
                destination = Path(directory) / "checkpoint"
                manifest = environment.save_checkpoint(destination)
                restored = environment.from_checkpoint(destination)
                self.assertEqual(
                    manifest["state_sha256"],
                    canonical_fingerprint(restored.snapshot()),
                )
                reference_itsm_recovery(restored)
                self.assertTrue(evaluate_itsm(restored)["passed"])
        finally:
            environment.close()


if __name__ == "__main__":
    unittest.main()
