from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ForgejoControlWorkflowTests(unittest.TestCase):
    def test_workflow_runs_reference_after_each_native_boundary(self):
        workflow = (
            ROOT / ".github" / "workflows" / "forgejo-source-audit.yml"
        ).read_text(encoding="utf-8")
        boundary = workflow.index("run_forgejo_merge_boundary.py")
        reference = workflow.index("run_forgejo_release_control.py")
        loop_end = workflow.index("          done", reference)
        self.assertLess(boundary, reference)
        self.assertLess(reference, loop_end)

    def test_reference_script_uses_public_environment_and_evaluator(self):
        script = (
            ROOT / "scripts" / "run_forgejo_release_control.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ForgejoReleaseEnvironment", script)
        self.assertIn("reference_forgejo_release_recovery", script)
        self.assertIn("evaluate_forgejo_release_recovery", script)


if __name__ == "__main__":
    unittest.main()
