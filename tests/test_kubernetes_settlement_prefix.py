from __future__ import annotations

import unittest

from aftermath_bench.integrations.kubernetes_settlement_prefix import (
    NAMESPACE,
    PRIOR_BATCH,
    PROTECTED_CRONJOB,
    SETTLEMENT_CRONJOB,
    TARGET_BATCH,
    TARGET_RECEIPT_SHA,
    prefix_manifests,
    settlement_job_manifest,
)


class KubernetesSettlementPrefixTest(unittest.TestCase):
    def test_prefix_has_a_real_multi_object_history(self) -> None:
        manifests = prefix_manifests()
        identities = {
            (item["kind"], item["metadata"]["name"])
            for item in manifests
        }
        self.assertGreaterEqual(len(manifests), 11)
        self.assertIn(("Namespace", NAMESPACE), identities)
        self.assertIn(("Job", PRIOR_BATCH), identities)
        self.assertIn(("CronJob", SETTLEMENT_CRONJOB), identities)
        self.assertIn(("CronJob", PROTECTED_CRONJOB), identities)
        self.assertIn(("Lease", PRIOR_BATCH), identities)

    def test_target_job_exposes_a_machine_readable_receipt(self) -> None:
        job = settlement_job_manifest()
        self.assertEqual(job["metadata"]["generateName"], f"{TARGET_BATCH}-")
        self.assertFalse(job["spec"]["suspend"])
        command = job["spec"]["template"]["spec"]["containers"][0][
            "command"
        ]
        self.assertIn(TARGET_RECEIPT_SHA, command[-1])
        self.assertEqual(
            job["spec"]["template"]["spec"]["restartPolicy"],
            "Never",
        )

    def test_suspended_job_is_a_native_controller_boundary(self) -> None:
        job = settlement_job_manifest(suspended=True)
        self.assertTrue(job["spec"]["suspend"])


if __name__ == "__main__":
    unittest.main()
