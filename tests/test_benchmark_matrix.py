from __future__ import annotations

import unittest

from aftermath_bench.benchmark_matrix import (
    load_benchmark_matrix,
    validate_benchmark_matrix,
)
from aftermath_bench.schema import repository_root


class BenchmarkMatrixTest(unittest.TestCase):
    def test_top_conference_matrix_has_144_planned_cases(self) -> None:
        matrix = load_benchmark_matrix(
            repository_root() / "data" / "benchmark_matrix.json"
        )
        report = validate_benchmark_matrix(matrix)
        self.assertTrue(report.passed, report.failures)
        self.assertEqual(report.observed["family_count"], 12)
        self.assertEqual(report.observed["target_case_count"], 144)
        self.assertEqual(report.observed["public_instance_count"], 12)
        self.assertEqual(report.observed["hidden_instance_count"], 24)


if __name__ == "__main__":
    unittest.main()
