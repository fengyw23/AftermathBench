from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aftermath_bench.integrations.forgejo_runtime import (
    checkout_and_verify,
    create_build_plan,
    materialize_pinned_containerfile,
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
        self.assertTrue(
            str(plan.pinned_containerfile).endswith(
                ".aftermath\\Dockerfile.pinned"
            )
            or str(plan.pinned_containerfile).endswith(
                ".aftermath/Dockerfile.pinned"
            )
        )
        self.assertGreaterEqual(len(plan.expected_hashes), 7)
        self.assertEqual(len(plan.base_images), 3)
        self.assertTrue(
            all(digest.startswith("sha256:") for _, digest, _ in plan.base_images)
        )
        self.assertIn(plan.revision, plan.fetch_commands[2])
        self.assertIn(str(plan.pinned_containerfile), plan.build_command)

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

    def test_pinned_containerfile_rewrites_every_base_image(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "forgejo"
            source.mkdir()
            plan = create_build_plan(source)
            (source / "Dockerfile").write_text(
                "FROM --platform=$BUILDPLATFORM "
                "data.forgejo.org/oci/xx AS xx\n"
                "FROM --platform=$BUILDPLATFORM "
                "data.forgejo.org/oci/golang:1.26-alpine3.23 "
                "AS build-env\n"
                "FROM data.forgejo.org/oci/alpine:3.23",
                encoding="utf-8",
            )
            result = materialize_pinned_containerfile(plan)
            pinned = plan.pinned_containerfile.read_text(encoding="utf-8")
        self.assertTrue(result["all_digests_pinned"])
        self.assertEqual(pinned.count("@sha256:"), 3)
        for reference, digest, _ in plan.base_images:
            self.assertIn(f"{reference}@{digest}", pinned)


if __name__ == "__main__":
    unittest.main()
