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


if __name__ == "__main__":
    unittest.main()
