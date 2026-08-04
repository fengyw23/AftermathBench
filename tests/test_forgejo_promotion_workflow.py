from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class ForgejoPromotionWorkflowTest(unittest.TestCase):
    def test_native_runtime_replays_and_audits_all_six_boundaries(self) -> None:
        text = (
            repository_root()
            / ".github"
            / "workflows"
            / "forgejo-promotion-runtime.yml"
        ).read_text(encoding="utf-8")
        ordered = (
            "build_forgejo_runtime.py",
            "manage_forgejo_stack.py up",
            "manage_forgejo_stack.py setup-runner",
            "build_forgejo_promotion_prefix.py",
            "snapshot-promotion-bundle",
            "run_forgejo_promotion_boundary.py",
            "run_forgejo_promotion_reference.py",
            "audit_forgejo_promotion_runtime.py",
        )
        positions = [text.index(value) for value in ordered]
        self.assertEqual(positions, sorted(positions))
        replay_block = text.split(
            "- name: Replay six source-grounded promotion boundaries", 1
        )[1].split("- name: Audit cross-system boundary variation", 1)[0]
        self.assertEqual(replay_block.count("_missing\n"), 3)
        self.assertIn("promotion_completed_response_lost", text)
        self.assertIn("--runner-disabled", text)
        self.assertNotIn("AFTERMATH_MODEL_API_KEY", text)
        self.assertNotIn("run-native-model", text)


if __name__ == "__main__":
    unittest.main()
