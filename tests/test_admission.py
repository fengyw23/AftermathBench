import unittest

from aftermath_bench.admission import validate_task
from aftermath_bench.schema import load_task, task_paths


class AdmissionTest(unittest.TestCase):
    def test_all_tasks_pass_hard_gate(self) -> None:
        for path in task_paths():
            with self.subTest(path=path):
                report = validate_task(load_task(path))
                self.assertTrue(report.passed, report.failures)


if __name__ == "__main__":
    unittest.main()
