from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from aftermath_bench.integrations.kubernetes_stack import KubernetesStack
from aftermath_bench.runtime_gate import (
    load_runtime_manifest,
    validate_runtime_manifest,
)
from aftermath_bench.schema import repository_root


class KubernetesRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = repository_root()
        self.lock = json.loads(
            (
                self.root
                / "runtimes"
                / "kubernetes"
                / "runtime.lock.json"
            ).read_text(encoding="utf-8")
        )

    def test_runtime_uses_pinned_kind_and_node_image(self) -> None:
        self.assertEqual(
            self.lock["kind"]["revision"],
            "9a205e8c8540557602240f8766d3c95c51c23c4c",
        )
        image = self.lock["kubernetes"]["node_image"]
        self.assertIn("kindest/node:v1.34.0@sha256:", image)
        self.assertEqual(len(image.rsplit("@sha256:", 1)[1]), 64)

    def test_kind_config_uses_the_locked_image(self) -> None:
        config = (
            self.root / "runtimes" / "kubernetes" / "kind-config.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(self.lock["kubernetes"]["node_image"], config)

    def test_source_and_execution_admission_are_complete(self) -> None:
        audit = json.loads(
            (
                self.root
                / "data"
                / "runtimes"
                / "kubernetes-v1.34"
                / "source_audit.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(len(audit["sources"]), 2)
        self.assertTrue(
            all(
                len(item["sha256"]) == 64
                for source in audit["sources"]
                for item in source["audited_paths"]
            )
        )
        manifest = load_runtime_manifest(
            self.root
            / "data"
            / "runtimes"
            / "kubernetes-v1.34"
            / "runtime.json"
        )
        report = validate_runtime_manifest(manifest)
        self.assertTrue(report.source_audit_passed)
        self.assertTrue(report.execution_admitted)
        self.assertTrue(
            report.execution_checks["admission_evidence_recorded"]
        )
        self.assertFalse(report.failures)
        self.assertNotIn("source_status_truthful", report.failures)
        self.assertNotIn("execution_status_truthful", report.failures)

    @patch("subprocess.run")
    @patch("shutil.which", return_value="available")
    def test_stack_create_uses_the_digest_pinned_image(
        self,
        _which,
        runner,
    ) -> None:
        def completed(command, **_kwargs):
            result = unittest.mock.Mock()
            result.returncode = 0
            result.stderr = ""
            if command[1:3] == ("get", "clusters"):
                result.stdout = ""
            elif "version" in command:
                result.stdout = json.dumps(
                    {"serverVersion": {"gitVersion": "v1.34.0"}}
                )
            else:
                result.stdout = ""
            return result

        runner.side_effect = completed
        stack = KubernetesStack.from_repository()
        status = stack.up()
        create = next(
            call.args[0]
            for call in runner.call_args_list
            if call.args[0][1:3] == ("create", "cluster")
        )
        self.assertIn(self.lock["kubernetes"]["node_image"], create)
        self.assertEqual(status["server_version"], "v1.34.0")


if __name__ == "__main__":
    unittest.main()
