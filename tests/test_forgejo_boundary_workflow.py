from __future__ import annotations

import unittest

from aftermath_bench.integrations.forgejo_faults import (
    FORGEJO_FAULT_VARIANTS,
)
from aftermath_bench.schema import repository_root


class ForgejoBoundaryWorkflowTest(unittest.TestCase):
    def test_workflow_replays_every_declared_variant(self) -> None:
        workflow = (
            repository_root()
            / ".github"
            / "workflows"
            / "forgejo-source-audit.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("run_forgejo_merge_boundary.py", workflow)
        for variant in FORGEJO_FAULT_VARIANTS:
            self.assertIn(variant, workflow)
        self.assertIn("release-prefix.tar.gz", workflow)

    def test_boundary_waits_for_native_delivery_to_leave_pending(self) -> None:
        script = (
            repository_root()
            / "scripts"
            / "run_forgejo_merge_boundary.py"
        ).read_text(encoding="utf-8")
        self.assertIn('delivery.status != "pending"', script)


if __name__ == "__main__":
    unittest.main()
