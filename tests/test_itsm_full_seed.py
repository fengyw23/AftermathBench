import os
import unittest

from aftermath_bench.scenarios.itsm_major_incident import (
    ITSM_VARIANTS,
    build_itsm_failure_state,
    reference_itsm_recovery,
    verify_itsm_sql,
)


ARCHIVE = os.environ.get("AFTERMATH_ENTERPRISEOPS_ARCHIVE")


@unittest.skipUnless(
    ARCHIVE,
    "set AFTERMATH_ENTERPRISEOPS_ARCHIVE to run the pinned full-seed test",
)
class ITSMFullSeedTest(unittest.TestCase):
    def test_all_variants_recover_on_complete_upstream_seed(self) -> None:
        for variant in ITSM_VARIANTS:
            with self.subTest(variant=variant):
                environment, _proxy, _failure = build_itsm_failure_state(
                    variant,
                    seed_archive=ARCHIVE,
                )
                try:
                    provenance = environment.snapshot()["seed_provenance"][0]
                    self.assertEqual(provenance[0], "enterpriseops_full_seed")
                    self.assertEqual(provenance[4], 24)
                    self.assertEqual(provenance[5], 241)
                    reference_itsm_recovery(environment)
                    self.assertTrue(verify_itsm_sql(environment)["passed"])
                finally:
                    environment.close()


if __name__ == "__main__":
    unittest.main()
