import unittest

from aftermath_bench.schema import repository_root


class ERPNextWorkflowSpecTest(unittest.TestCase):
    def setUp(self) -> None:
        workflow = repository_root() / ".github" / "workflows" / "erpnext-native.yml"
        self.workflow = workflow.read_text(encoding="utf-8")

    def test_hidden_runtime_evidence_is_uploaded(self) -> None:
        self.assertIn("include-hidden-files: true", self.workflow)

    def test_compose_log_is_visible_in_job_output(self) -> None:
        self.assertIn(
            "tail -n 500 runtimes/erpnext/.runtime/compose.log",
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
