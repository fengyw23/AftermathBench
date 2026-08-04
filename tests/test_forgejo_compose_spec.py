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
        self.assertIn(
            "provenance-webhook-fault-gateway:", self.compose
        )
        self.assertIn("webhook-sink:", self.compose)
        self.assertIn("deployment-target:", self.compose)
        self.assertIn("deployment-fault-gateway:", self.compose)
        self.assertIn("runtime_services.deployment_target", self.compose)
        self.assertIn("runtime_services.webhook_sink", self.compose)
        self.assertIn("AFTERMATH_GATEWAY_UPSTREAM: http://forgejo:3000", self.compose)
        self.assertIn(
            "FORGEJO__server__ROOT_URL: http://forgejo:3000/", self.compose
        )
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

    def test_actions_runner_is_open_source_digest_pinned_and_socketless(self) -> None:
        runtime = repository_root() / "runtimes" / "forgejo"
        runner = json.loads(
            (runtime / "runner.lock.json").read_text(encoding="utf-8")
        )
        self.assertEqual(runner["source"]["license"], "MIT")
        self.assertEqual(
            runner["source"]["revision"],
            "33e0ab7b6891adba1aea650b9b59f471bab352b0",
        )
        pinned = (
            f'{runner["image"]["reference"]}@'
            f'{runner["image"]["digest"]}'
        )
        runner_containerfile = (
            runtime / "runner" / "Containerfile"
        ).read_text(encoding="utf-8")
        self.assertIn(pinned, runner_containerfile)
        self.assertIn(
            runner["runtime_dependencies"]["nodejs"]["artifact_url"],
            runner_containerfile,
        )
        self.assertIn(
            "--checksum=sha256:"
            + runner["runtime_dependencies"]["nodejs"]["sha256"],
            runner_containerfile,
        )
        self.assertIn(
            "dockerfile: runtimes/forgejo/runner/Containerfile", self.compose
        )
        self.assertNotIn("/var/run/docker.sock", self.compose)
        self.assertFalse(runner["docker_socket_mounted"])


if __name__ == "__main__":
    unittest.main()
