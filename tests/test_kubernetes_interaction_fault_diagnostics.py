from __future__ import annotations

import unittest
from unittest.mock import Mock

from aftermath_bench.integrations.kubernetes_interaction_faults import (
    KubernetesInteractionFaultBoundary,
)


class KubernetesInteractionFaultDiagnosticTests(unittest.TestCase):
    def test_migration_timeout_reports_job_pod_and_event_state(self) -> None:
        api = Mock()
        api.create.return_value = {
            "metadata": {"name": "migration-abc", "uid": "uid-job"}
        }
        api.wait_condition.side_effect = RuntimeError("timed out")
        api.get.return_value = {
            "metadata": {"name": "migration-abc", "uid": "uid-job"},
            "status": {"active": 1},
        }
        api.list.return_value = [
            {
                "metadata": {"name": "migration-abc-pod"},
                "status": {"phase": "Pending", "reason": "Unschedulable"},
            }
        ]
        api.events.return_value = [
            {
                "reason": "FailedScheduling",
                "message": "no ready scheduler",
                "involvedObject": {
                    "name": "migration-abc-pod",
                    "uid": "uid-pod",
                },
            }
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            '"reason":"Unschedulable".*"reason":"FailedScheduling"',
        ):
            KubernetesInteractionFaultBoundary(api)._migration("failed")


if __name__ == "__main__":
    unittest.main()
