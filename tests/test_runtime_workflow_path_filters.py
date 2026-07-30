from __future__ import annotations

import unittest
from pathlib import Path


class RuntimeWorkflowPathFilterTests(unittest.TestCase):
    def test_expensive_kubernetes_replays_are_path_scoped(self) -> None:
        workflows = {
            "kubernetes-interaction-runtime.yml": (
                "kubernetes_interaction_*.py"
            ),
            "kubernetes-constraint-runtime.yml": (
                "kubernetes_constraint_*.py"
            ),
            "kubernetes-migration-runtime.yml": (
                "kubernetes_migration_*.py"
            ),
        }
        for name, family_pattern in workflows.items():
            with self.subTest(workflow=name):
                text = (
                    Path(".github/workflows") / name
                ).read_text(encoding="utf-8")
                self.assertIn("paths:", text)
                self.assertIn(family_pattern, text)
                self.assertIn("runtimes/kubernetes/**", text)
                self.assertIn("native_admission.py", text)


if __name__ == "__main__":
    unittest.main()
