import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from aftermath_bench.core import canonical_fingerprint
from aftermath_bench.scenarios.release_migration import (
    RELEASE_VARIANTS,
    build_release_failure_state,
    evaluate_release,
    reference_release_recovery,
)


class ReleaseMigrationTest(unittest.TestCase):
    def test_all_matched_variants_recover(self) -> None:
        for variant in RELEASE_VARIANTS:
            with self.subTest(variant=variant):
                environment, proxy, failure = build_release_failure_state(variant)
                try:
                    self.assertEqual(failure, {"ok": False, "error": "504 Gateway Timeout"})
                    reference_release_recovery(environment)
                    self.assertTrue(evaluate_release(environment.snapshot())["passed"])
                    self.assertEqual(len(proxy.events), 1)
                finally:
                    environment.close()

    def test_blind_retry_damages_committed_variant(self) -> None:
        environment, _proxy, _failure = build_release_failure_state(
            "commit_response_lost"
        )
        try:
            environment.invoke("deploy_release", version=environment.VERSION)
            self.assertFalse(evaluate_release(environment.snapshot())["protocol_safety"])
        finally:
            environment.close()

    def test_goal_only_partial_repair_is_not_integrity_complete(self) -> None:
        environment, _proxy, _failure = build_release_failure_state("partial_commit")
        try:
            environment.invoke(
                "reconcile_partial_rollout",
                version=environment.VERSION,
            )
            result = evaluate_release(environment.snapshot())
            self.assertFalse(result["goal_completion"])
            self.assertFalse(result["repair_completeness"])
        finally:
            environment.close()

    def test_failure_checkpoint_round_trip_is_identical(self) -> None:
        environment, _proxy, _failure = build_release_failure_state("partial_commit")
        try:
            with TemporaryDirectory() as directory:
                destination = Path(directory) / "checkpoint"
                manifest = environment.save_checkpoint(destination)
                restored = environment.from_checkpoint(destination)
                self.assertEqual(
                    manifest["state_sha256"],
                    canonical_fingerprint(restored.snapshot()),
                )
                reference_release_recovery(restored)
                self.assertTrue(evaluate_release(restored.snapshot())["passed"])
        finally:
            environment.close()


if __name__ == "__main__":
    unittest.main()
