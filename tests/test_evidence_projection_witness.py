from __future__ import annotations

import unittest

from aftermath_bench.evidence_projection import projection_admission_report


class EvidenceProjectionWitnessTest(unittest.TestCase):
    def test_finds_decisive_fact_group_witnesses(self) -> None:
        report = projection_admission_report(
            variant_facts={
                "failed_clean": {"commit": False, "prepare": False, "release": False},
                "failed_prepared": {
                    "commit": False,
                    "prepare": True,
                    "release": False,
                },
                "committed_unpublished": {
                    "commit": True,
                    "prepare": False,
                    "release": False,
                },
                "committed_published": {
                    "commit": True,
                    "prepare": False,
                    "release": True,
                },
            },
            variant_scopes={
                "failed_clean": "cleanup",
                "failed_prepared": "compensate_cleanup",
                "committed_unpublished": "publish",
                "committed_published": "close",
            },
            evidence_fact_groups={
                "commit_state": ["commit"],
                "preparation_state": ["prepare"],
                "publication_state": ["release"],
            },
        )
        self.assertTrue(report["all_declared_groups_have_witnesses"])
        self.assertEqual(report["projection_witness_count"], 3)

    def test_redundant_group_is_not_counted_as_required(self) -> None:
        report = projection_admission_report(
            variant_facts={
                "left": {"commit": False, "region": "us"},
                "right": {"commit": True, "region": "us"},
            },
            variant_scopes={"left": "cleanup", "right": "complete"},
            evidence_fact_groups={
                "commit_state": ["commit"],
                "region": ["region"],
            },
        )
        self.assertFalse(report["all_declared_groups_have_witnesses"])
        self.assertIsNone(report["witnesses"]["region"])

    def test_requires_identical_variant_coverage(self) -> None:
        with self.assertRaisesRegex(ValueError, "same variants"):
            projection_admission_report(
                variant_facts={"left": {"commit": False}},
                variant_scopes={},
                evidence_fact_groups={"commit": ["commit"]},
            )


if __name__ == "__main__":
    unittest.main()
