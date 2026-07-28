import unittest

from aftermath_bench.admission import validate_task
from aftermath_bench.schema import load_task


class AdmissionTest(unittest.TestCase):
    def test_reference_task_passes_hard_gate(self) -> None:
        report = validate_task(load_task())
        self.assertTrue(report.passed, report.failures)


if __name__ == "__main__":
    unittest.main()

