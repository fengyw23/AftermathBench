from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aftermath_bench.integrations.forgejo_runtime import (
    checkout_and_verify,
    create_build_plan,
)


class ForgejoRuntimeTest(unittest.TestCase):
    def test_plan_pins_revision_and_audited_hashes(self) -> None:
        with TemporaryDirectory() as directory:
            plan = create_build_plan(Path(directory) / "forgejo")
        self.assertEqual(
            plan.revision,
            "fbafae6c6288f3448aa6932576841f5daf5a9c76",
        )
        self.assertEqual(plan.containerfile, "Dockerfile")
        self.assertGreaterEqual(len(plan.expected_hashes), 7)
        self.assertIn(plan.revision, plan.fetch_commands[2])

    def test_checkout_rejects_nonempty_directory(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "forgejo"
            source.mkdir()
            (source / "existing").write_text("occupied", encoding="utf-8")
            plan = create_build_plan(source)
            with patch("subprocess.run") as runner, self.assertRaisesRegex(
                RuntimeError,
                "refusing to reuse non-empty",
            ):
                checkout_and_verify(plan)
            runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
