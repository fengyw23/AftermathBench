import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from aftermath_bench.integrations.erpnext_faults import (
    ComposeWorkerControl,
    ERPNextFaultController,
)


class ERPNextFaultControllerTest(unittest.TestCase):
    def _controller(self):
        calls = []
        worker = Mock()

        def requester(base_url, method, path, payload):
            calls.append((base_url, method, path, payload))
            if base_url.endswith("9091"):
                return {"mode": payload["mode"]}
            if method == "GET":
                return {
                    "name": "redis_queue",
                    "listen": "0.0.0.0:26379",
                    "upstream": "redis-queue:6379",
                    "enabled": True,
                }
            return payload

        return (
            ERPNextFaultController(
                worker_control=worker,
                requester=requester,
            ),
            worker,
            calls,
        )

    def test_response_loss_uses_gateway_not_queue_corruption(self) -> None:
        controller, worker, calls = self._controller()
        controller.arm("database_committed_response_lost")
        self.assertIn(
            (
                "http://127.0.0.1:9091",
                "PUT",
                "/mode",
                {"mode": "drop_response"},
            ),
            calls,
        )
        queue_updates = [
            call[3]["enabled"]
            for call in calls
            if call[1] == "POST" and call[2] == "/proxies/redis_queue"
        ]
        self.assertEqual(queue_updates, [True])
        worker.stop.assert_not_called()

    def test_after_commit_failure_disables_only_queue_proxy(self) -> None:
        controller, _worker, calls = self._controller()
        controller.arm("after_commit_enqueue_failed")
        queue_updates = [
            call[3]["enabled"]
            for call in calls
            if call[1] == "POST" and call[2] == "/proxies/redis_queue"
        ]
        self.assertEqual(queue_updates, [True, False])
        self.assertIn(
            (
                "http://127.0.0.1:9091",
                "PUT",
                "/mode",
                {"mode": "drop_response"},
            ),
            calls,
        )

    def test_async_pending_stops_workers_and_disarm_keeps_them_stopped(self) -> None:
        controller, worker, _calls = self._controller()
        controller.arm("async_job_pending")
        worker.stop.assert_called_once()
        self.assertIn(
            (
                "http://127.0.0.1:9091",
                "PUT",
                "/mode",
                {"mode": "drop_response"},
            ),
            _calls,
        )
        worker.start.reset_mock()
        controller.disarm_transport_after_failure("async_job_pending")
        worker.start.assert_not_called()

    def test_compose_worker_command_is_closed_and_task_scoped(self) -> None:
        runner = Mock(return_value=subprocess.CompletedProcess([], 0))
        with tempfile.TemporaryDirectory() as directory:
            compose = Path(directory) / "compose.yaml"
            control = ComposeWorkerControl(compose, runner=runner)
            control.stop()
        command = runner.call_args.args[0]
        self.assertEqual(command[0:2], ("docker", "compose"))
        self.assertEqual(command[-3:], ("stop", "queue-short", "queue-long"))


if __name__ == "__main__":
    unittest.main()
