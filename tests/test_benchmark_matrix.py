from __future__ import annotations

import copy
import unittest

from aftermath_bench.benchmark_matrix import (
    load_benchmark_matrix,
    validate_benchmark_matrix,
)
from aftermath_bench.schema import repository_root


class BenchmarkMatrixTest(unittest.TestCase):
    def load_matrix(self) -> dict:
        return load_benchmark_matrix(
            repository_root() / "data" / "benchmark_matrix.json"
        )

    def test_top_conference_matrix_uses_family_specific_case_counts(self) -> None:
        matrix = self.load_matrix()
        report = validate_benchmark_matrix(matrix)
        self.assertTrue(report.passed, report.failures)
        self.assertEqual(report.observed["family_count"], 12)
        self.assertEqual(report.observed["target_case_count"], 183)
        self.assertEqual(report.observed["public_instance_count"], 12)
        self.assertEqual(report.observed["hidden_instance_count"], 24)

    def test_duplicate_instance_id_is_rejected(self) -> None:
        matrix = self.load_matrix()
        family = matrix["domains"][0]["families"][0]
        family["instances"][1]["id"] = family["instances"][0]["id"]
        report = validate_benchmark_matrix(matrix)
        self.assertFalse(report.passed)
        self.assertFalse(
            report.checks["instance_ids_unique_within_family"]
        )

    def test_self_declared_smaller_release_profile_is_rejected(self) -> None:
        matrix = self.load_matrix()
        domain = copy.deepcopy(matrix["domains"][0])
        domain["families"] = [domain["families"][0]]
        domain["families"][0]["instances"] = [
            {"id": "dev-001", "split": "public_dev"},
            {"id": "test-001", "split": "hidden_test"},
        ]
        matrix["domains"] = [domain]
        matrix["release_requirements"] = {
            "domain_count": 1,
            "families_per_domain": 1,
            "instances_per_family": 2,
            "public_dev_per_family": 1,
            "hidden_test_per_family": 1,
        }

        report = validate_benchmark_matrix(matrix)

        self.assertFalse(report.passed)
        self.assertFalse(
            report.checks["release_requirements_match_fixed_profile"]
        )
        self.assertFalse(report.checks["domain_ids_match_fixed_profile"])
        self.assertFalse(report.checks["slot_contract_matches_fixed_profile"])
        self.assertFalse(
            report.checks["target_case_count_matches_fixed_profile"]
        )

    def test_unknown_release_profile_is_rejected(self) -> None:
        matrix = self.load_matrix()
        matrix["target_release"] = "top-conference-mini"

        report = validate_benchmark_matrix(matrix)

        self.assertFalse(report.passed)
        self.assertFalse(report.checks["target_release_profile_known"])
        self.assertFalse(
            report.checks["release_requirements_match_fixed_profile"]
        )

    def test_family_id_mutation_is_rejected(self) -> None:
        matrix = self.load_matrix()
        matrix["domains"][0]["families"][0]["family_id"] = (
            "erpnext-renamed-family"
        )

        report = validate_benchmark_matrix(matrix)

        self.assertFalse(report.passed)
        self.assertFalse(
            report.checks["family_variant_contract_matches_fixed_profile"]
        )
        self.assertFalse(report.checks["slot_contract_matches_fixed_profile"])

    def test_split_swap_that_preserves_quotas_is_rejected(self) -> None:
        matrix = self.load_matrix()
        instances = matrix["domains"][0]["families"][0]["instances"]
        instances[0]["split"], instances[1]["split"] = (
            instances[1]["split"],
            instances[0]["split"],
        )

        report = validate_benchmark_matrix(matrix)

        self.assertFalse(report.passed)
        self.assertTrue(report.checks["split_quota_matches_requirement"])
        self.assertFalse(report.checks["slot_contract_matches_fixed_profile"])

    def test_family_variant_count_mutation_is_rejected(self) -> None:
        matrix = self.load_matrix()
        matrix["domains"][1]["families"][1]["variant_profile"][
            "required_variant_count"
        ] = 7

        report = validate_benchmark_matrix(matrix)

        self.assertFalse(report.passed)
        self.assertFalse(
            report.checks["family_variant_contract_matches_fixed_profile"]
        )
        self.assertFalse(
            report.checks["target_case_count_matches_fixed_profile"]
        )

    def test_semantic_minimum_mutation_is_rejected(self) -> None:
        matrix = self.load_matrix()
        matrix["domains"][2]["families"][2]["variant_profile"][
            "minimum_recovery_signatures"
        ] = 3

        report = validate_benchmark_matrix(matrix)

        self.assertFalse(report.passed)
        self.assertFalse(
            report.checks["semantic_contract_matches_fixed_profile"]
        )


if __name__ == "__main__":
    unittest.main()
