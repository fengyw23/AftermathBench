from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class ForgejoPromotionModelWorkflowTest(unittest.TestCase):
    def test_restores_every_native_boundary_and_uses_secret(self) -> None:
        workflow = (
            repository_root()
            / ".github"
            / "workflows"
            / "forgejo-promotion-model.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("ZHIPU_CODING_API_KEY", workflow)
        self.assertIn("run-native-model", workflow)
        self.assertIn("restore-promotion-bundle", workflow)
        self.assertIn("boundary-$variant", workflow)
        self.assertIn("--expected-execution-control", workflow)
        self.assertIn("github.event_name == 'push'", workflow)
        self.assertIn("native-hard-recovery-v1", workflow)
        self.assertNotIn("recovery_signature_class", workflow)


if __name__ == "__main__":
    unittest.main()
