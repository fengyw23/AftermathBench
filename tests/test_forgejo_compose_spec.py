from __future__ import annotations

import json
import unittest

from aftermath_bench.schema import repository_root


class ForgejoComposeSpecTest(unittest.TestCase):
    def setUp(self) -> None:
        runtime = repository_root() / "runtimes" / "forgejo"
        self.compose = (runtime / "compose.yaml").read_text(encoding="utf-8")
        self.lock = json.loads(
            (runtime / "runtime.lock.json").read_text(encoding="utf-8")
        )

    def test_stack_uses_source_built_forgejo_and_two_fault_observers(
        self,
    ) -> None:
        self.assertIn("pull_policy: never", self.compose)
        self.assertIn("api-fault-gateway:", self.compose)
        self.assertIn("webhook-fault-gateway:", self.compose)
        self.assertIn("webhook-sink:", self.compose)
        self.assertIn("runtime_services.webhook_sink", self.compose)
        self.assertIn("AFTERMATH_GATEWAY_UPSTREAM: http://forgejo:3000", self.compose)
        self.assertIn(
            "AFTERMATH_GATEWAY_UPSTREAM: http://webhook-sink:8080",
            self.compose,
        )

    def test_every_build_and_control_base_is_digest_pinned(self) -> None:
        self.assertEqual(
            self.lock["base_image_digest_status"],
            "resolved",
        )
        for image in self.lock["base_images"].values():
            self.assertTrue(image["digest"].startswith("sha256:"))
        control = self.lock["infrastructure_images"]["control_base"]
        pinned = f'{control["reference"]}@{control["digest"]}'
        containerfile = (
            repository_root()
            / "runtimes"
            / "forgejo"
            / "control"
            / "Containerfile"
        ).read_text(encoding="utf-8")
        self.assertIn(pinned, containerfile)


if __name__ == "__main__":
    unittest.main()
