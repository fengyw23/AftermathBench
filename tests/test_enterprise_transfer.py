import unittest

from aftermath_bench.evaluator import evaluate
from aftermath_bench.scenarios.enterprise_transfer import (
    VARIANTS,
    EnterpriseTransferEnv,
    reference_recovery,
)


class EnterpriseTransferTest(unittest.TestCase):
    def test_reference_recovery_passes_every_variant(self) -> None:
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                env = EnterpriseTransferEnv(variant)
                reference_recovery(env)
                self.assertTrue(evaluate(env.snapshot()).passed)

    def test_blind_retry_fails_committed_variant(self) -> None:
        env = EnterpriseTransferEnv("commit_response_lost")
        env.invoke("remove_membership", membership_id="old-engineering")
        self.assertFalse(evaluate(env.snapshot()).protocol_safety)

    def test_fixing_only_one_partial_write_is_incomplete(self) -> None:
        env = EnterpriseTransferEnv("not_committed")
        env.invoke("remove_membership", membership_id="old-engineering")
        result = evaluate(env.snapshot())
        self.assertFalse(result.integrity)
        self.assertFalse(result.repair_completeness)

    def test_damaging_protected_state_is_detected(self) -> None:
        env = EnterpriseTransferEnv("not_committed")
        env.state["memberships"].pop("new-research")
        self.assertFalse(evaluate(env.snapshot()).preservation)


if __name__ == "__main__":
    unittest.main()

