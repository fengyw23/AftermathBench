from __future__ import annotations

import subprocess

from aftermath_bench.integrations.erpnext_stack import ERPNextStack


def test_restore_keeps_stateless_http_services_running(tmp_path):
    snapshot = tmp_path / "prefix.sql"
    snapshot.write_bytes(b"-- deterministic test snapshot\n")
    commands: list[tuple[str, ...]] = []

    def runner(command, **kwargs):
        commands.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, "", "")

    stack = ERPNextStack(
        compose_file=tmp_path / "compose.yaml",
        runner=runner,
    )
    stack._wait_http_service = lambda *args, **kwargs: None  # type: ignore[method-assign]
    stack._reset_http_service = lambda *args, **kwargs: None  # type: ignore[method-assign]
    stack.restore_database(snapshot)

    stop = next(command for command in commands if "stop" in command)
    start = next(command for command in commands if "start" in command)
    assert stop[-3:] == ("stop", "queue-short", "queue-long")
    assert start[-3:] == ("start", "queue-short", "queue-long")
    for service in ("backend", "frontend", "fault-gateway", "websocket"):
        assert service not in stop
        assert service not in start

