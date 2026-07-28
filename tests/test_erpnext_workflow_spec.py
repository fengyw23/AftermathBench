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

    def test_ephemeral_credentials_are_removed_and_never_uploaded(self) -> None:
        self.assertIn(
            "rm -f runtimes/erpnext/.runtime/credentials.json",
            self.workflow,
        )
        upload_section = self.workflow.split(
            "- name: Upload native-runtime evidence",
            maxsplit=1,
        )[1]
        self.assertNotIn("credentials.json", upload_section)
        self.assertNotIn(".runtime/*.json", upload_section)


if __name__ == "__main__":
    unittest.main()
