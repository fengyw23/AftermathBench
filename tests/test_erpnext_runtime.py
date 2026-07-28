import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aftermath_bench.integrations.erpnext_runtime import (
    create_build_plan,
    load_runtime_lock,
    verify_source_refs,
)


class ERPNextRuntimeTest(unittest.TestCase):
    def test_build_plan_uses_pinned_public_tags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "frappe_docker"
            plan = create_build_plan(source)
        lock = load_runtime_lock()
        command = plan.build_command
        self.assertEqual(plan.image, "aftermathbench/erpnext:v15.118.1")
        self.assertIn("FRAPPE_BRANCH=v15.116.0", command)
        self.assertIn("ERPNEXT_BRANCH=v15.118.1", command)
        self.assertIn(lock["build_driver"]["revision"], plan.fetch_commands[2])
        self.assertEqual(
            plan.source_refs,
            (
                (
                    "https://github.com/frappe/frappe",
                    "v15.116.0",
                    "c1afa13e12834dcdc1d82c4ba8bb3e5652163656",
                ),
                (
                    "https://github.com/frappe/erpnext",
                    "v15.118.1",
                    "b9c9b76f5b043bd542b01dd4fefe913416a7bb53",
                ),
            ),
        )

    def test_build_plan_does_not_use_a_prebuilt_erpnext_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = create_build_plan(Path(directory) / "frappe_docker")
        rendered = " ".join(plan.build_command)
        self.assertIn("images/production/Containerfile", rendered)
        self.assertNotIn("frappe/erpnext:", rendered)

    @patch("subprocess.check_output")
    def test_source_tags_are_checked_against_locked_commits(self, check_output) -> None:
        lock = load_runtime_lock()
        check_output.side_effect = [
            f"{lock['frappe']['revision']}\trefs/tags/{lock['frappe']['tag']}\n",
            f"{lock['erpnext']['revision']}\trefs/tags/{lock['erpnext']['tag']}\n",
        ]
        with tempfile.TemporaryDirectory() as directory:
            plan = create_build_plan(Path(directory) / "frappe_docker")
        verify_source_refs(plan)
        self.assertEqual(check_output.call_count, 2)


if __name__ == "__main__":
    unittest.main()
