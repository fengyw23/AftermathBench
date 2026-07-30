from __future__ import annotations

import json
import unittest

from aftermath_bench.kubernetes_pairing import (
    task_prefix_projection,
    task_prefix_sha256,
)
from aftermath_bench.schema import repository_root


class KubernetesPairingTest(unittest.TestCase):
    def test_task_projection_ignores_only_runtime_root_ca(self) -> None:
        base = {
            "scenario_id": "example",
            "fingerprint": "raw-a",
            "state": {
                "objects": [
                    {
                        "kind": "ConfigMap",
                        "metadata": {"name": "kube-root-ca.crt"},
                        "data": {"ca.crt": "certificate-a"},
                    },
                    {
                        "kind": "ConfigMap",
                        "metadata": {"name": "task-contract"},
                        "data": {"epoch": "2"},
                    },
                ]
            },
        }
        other = json.loads(json.dumps(base))
        other["fingerprint"] = "raw-b"
        other["state"]["objects"][0]["data"]["ca.crt"] = "certificate-b"
        self.assertEqual(task_prefix_sha256(base), task_prefix_sha256(other))

        other["state"]["objects"][1]["data"]["epoch"] = "3"
        self.assertNotEqual(task_prefix_sha256(base), task_prefix_sha256(other))
        projected = task_prefix_projection(base)
        self.assertNotIn("fingerprint", projected)
        self.assertEqual(len(projected["state"]["objects"]), 1)

    def test_control_and_ordinary_primary_have_same_task_state(self) -> None:
        root = repository_root()
        control = json.loads(
            (
                root
                / "data"
                / "evidence"
                / "kubernetes-interaction-control-valid-20260730"
                / "prefix.json"
            ).read_text(encoding="utf-8")
        )
        expected = "0d874013374de673660bad82e7b8330d5d4c88dd529455a377c4478328a9dfca"
        self.assertEqual(task_prefix_sha256(control), expected)


if __name__ == "__main__":
    unittest.main()
