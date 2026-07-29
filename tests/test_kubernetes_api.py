from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from aftermath_bench.integrations.kubernetes_api import KubernetesApi


class KubernetesApiTest(unittest.TestCase):
    @patch("subprocess.run")
    def test_patch_is_an_ordinary_kubectl_merge_patch(self, runner) -> None:
        runner.return_value.returncode = 0
        runner.return_value.stdout = json.dumps(
            {"metadata": {"name": "checkout"}}
        )
        runner.return_value.stderr = ""
        api = KubernetesApi()
        result = api.patch(
            "deployment",
            "checkout",
            {"spec": {"template": {"metadata": {"labels": {"release": "v2"}}}}},
            namespace="aftermath-rollout",
        )
        command = runner.call_args.args[0]
        self.assertEqual(result["metadata"]["name"], "checkout")
        self.assertIn("patch", command)
        self.assertIn("--type", command)
        self.assertIn("merge", command)
        self.assertNotIn("repair", " ".join(command))

    @patch("subprocess.run")
    def test_apply_uses_stdin_and_returns_native_object(self, runner) -> None:
        runner.return_value.returncode = 0
        runner.return_value.stdout = json.dumps(
            {"kind": "ConfigMap", "metadata": {"name": "release-config"}}
        )
        runner.return_value.stderr = ""
        api = KubernetesApi()
        result = api.apply(
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": "release-config"},
            }
        )
        self.assertEqual(result["kind"], "ConfigMap")
        self.assertIn("-f", runner.call_args.args[0])
        self.assertIn("release-config", runner.call_args.kwargs["input"])

    @patch("subprocess.run")
    def test_create_supports_server_generated_native_names(self, runner) -> None:
        runner.return_value.returncode = 0
        runner.return_value.stdout = json.dumps(
            {
                "kind": "Job",
                "metadata": {"name": "settlement-2026-07-x7k2p"},
            }
        )
        runner.return_value.stderr = ""
        api = KubernetesApi()
        result = api.create(
            {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "metadata": {"generateName": "settlement-2026-07-"},
            }
        )
        self.assertEqual(result["metadata"]["name"], "settlement-2026-07-x7k2p")
        self.assertIn("create", runner.call_args.args[0])
        self.assertIn("generateName", runner.call_args.kwargs["input"])

    @patch("subprocess.run")
    def test_node_taints_use_native_kubectl_commands(self, runner) -> None:
        runner.return_value.returncode = 0
        runner.return_value.stdout = "node/node-1 tainted"
        runner.return_value.stderr = ""
        api = KubernetesApi()
        api.taint_node(
            "node-1",
            "aftermath.dev/rollout-pending=true:NoSchedule",
        )
        taint_command = runner.call_args.args[0]
        self.assertIn("taint", taint_command)
        self.assertIn("node-1", taint_command)
        self.assertIn("--overwrite", taint_command)
        api.remove_node_taint(
            "node-1", "aftermath.dev/rollout-pending"
        )
        remove_command = runner.call_args.args[0]
        self.assertIn("aftermath.dev/rollout-pending-", remove_command)

    @patch("subprocess.run")
    def test_job_wait_and_logs_are_ordinary_kubectl_reads(self, runner) -> None:
        runner.return_value.returncode = 0
        runner.return_value.stdout = "completed\n"
        runner.return_value.stderr = ""
        api = KubernetesApi()
        api.wait_condition(
            "job",
            "settlement-2026-07",
            condition="complete",
            namespace="aftermath-settlement",
            timeout="30s",
        )
        wait_command = runner.call_args.args[0]
        self.assertIn("wait", wait_command)
        self.assertIn("--for=condition=complete", wait_command)
        self.assertIn("job/settlement-2026-07", wait_command)
        self.assertIn("--timeout=30s", wait_command)

        output = api.logs(
            "job",
            "settlement-2026-07",
            namespace="aftermath-settlement",
        )
        log_command = runner.call_args.args[0]
        self.assertEqual(output, "completed\n")
        self.assertIn("logs", log_command)
        self.assertIn("job/settlement-2026-07", log_command)


if __name__ == "__main__":
    unittest.main()
