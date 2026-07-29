from __future__ import annotations

import http.client
import json
import os
import socket
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


MODES = ("normal", "suppress_request", "drop_response")
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class GatewayState:
    def __init__(self) -> None:
        self._mode = "normal"
        self._lock = threading.Lock()

    def get(self) -> str:
        with self._lock:
            return self._mode

    def set(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"unsupported gateway mode: {mode}")
        with self._lock:
            self._mode = mode


class GatewayAuditStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS gateway_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    correlation_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    upstream_status INTEGER,
                    outcome TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def record(
        self,
        *,
        correlation_id: str,
        method: str,
        path: str,
        mode: str,
        upstream_status: int | None,
        outcome: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO gateway_events(
                    correlation_id, recorded_at, method, path, mode,
                    upstream_status, outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    correlation_id,
                    datetime.now(timezone.utc).isoformat(),
                    method,
                    path,
                    mode,
                    upstream_status,
                    outcome,
                ),
            )

    def events(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM gateway_events ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]

    def reset(self) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM gateway_events")


def _close_without_response(handler: BaseHTTPRequestHandler) -> None:
    handler.close_connection = True
    try:
        handler.connection.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    handler.connection.close()


def make_gateway_handler(
    *,
    upstream_url: str,
    state: GatewayState,
    audit: GatewayAuditStore,
    upstream_host_header: str | None = None,
) -> type[BaseHTTPRequestHandler]:
    upstream = urlsplit(upstream_url)
    if upstream.scheme != "http" or not upstream.hostname:
        raise ValueError("gateway currently requires an http upstream URL")
    upstream_port = upstream.port or 80

    class GatewayHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _handle(self) -> None:
            mode = state.get()
            correlation_id = self.headers.get(
                "X-Aftermath-Correlation-ID",
                str(uuid.uuid4()),
            )
            if mode == "suppress_request":
                audit.record(
                    correlation_id=correlation_id,
                    method=self.command,
                    path=self.path,
                    mode=mode,
                    upstream_status=None,
                    outcome="request_suppressed",
                )
                _close_without_response(self)
                return

            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else None
            headers = {
                name: value
                for name, value in self.headers.items()
                if name.lower() not in HOP_BY_HOP_HEADERS
                and name.lower() != "host"
            }
            headers["Host"] = upstream_host_header or upstream.netloc
            headers["X-Aftermath-Correlation-ID"] = correlation_id
            connection = http.client.HTTPConnection(
                upstream.hostname,
                upstream_port,
                timeout=120,
            )
            try:
                connection.request(
                    self.command,
                    self.path,
                    body=body,
                    headers=headers,
                )
                response = connection.getresponse()
                response_body = response.read()
                response_headers = response.getheaders()
                status = response.status
            except Exception:
                audit.record(
                    correlation_id=correlation_id,
                    method=self.command,
                    path=self.path,
                    mode=mode,
                    upstream_status=None,
                    outcome="upstream_error",
                )
                raise
            finally:
                connection.close()

            if mode == "drop_response":
                audit.record(
                    correlation_id=correlation_id,
                    method=self.command,
                    path=self.path,
                    mode=mode,
                    upstream_status=status,
                    outcome="upstream_completed_response_dropped",
                )
                _close_without_response(self)
                return

            audit.record(
                correlation_id=correlation_id,
                method=self.command,
                path=self.path,
                mode=mode,
                upstream_status=status,
                outcome="response_forwarded",
            )
            self.send_response(status)
            for name, value in response_headers:
                if name.lower() not in HOP_BY_HOP_HEADERS:
                    self.send_header(name, value)
            self.send_header("X-Aftermath-Correlation-ID", correlation_id)
            self.end_headers()
            self.wfile.write(response_body)

        do_GET = _handle
        do_POST = _handle
        do_PATCH = _handle
        do_PUT = _handle
        do_DELETE = _handle

    return GatewayHandler


def make_control_handler(
    state: GatewayState,
    audit: GatewayAuditStore | None = None,
) -> type[BaseHTTPRequestHandler]:
    class ControlHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _respond(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/mode":
                self._respond(200, {"mode": state.get()})
                return
            if self.path == "/audit" and audit is not None:
                self._respond(200, {"events": audit.events()})
                return
            self._respond(404, {"error": "not_found"})

        def do_PUT(self) -> None:
            if self.path != "/mode":
                self._respond(404, {"error": "not_found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length))
                state.set(str(payload["mode"]))
            except (ValueError, KeyError, json.JSONDecodeError):
                self._respond(400, {"error": "invalid_mode", "allowed": MODES})
                return
            self._respond(200, {"mode": state.get()})

        def do_DELETE(self) -> None:
            if self.path != "/admin/reset" or audit is None:
                self._respond(404, {"error": "not_found"})
                return
            state.set("normal")
            audit.reset()
            self._respond(200, {"ok": True, "mode": state.get()})

    return ControlHandler


def main() -> None:
    state = GatewayState()
    audit = GatewayAuditStore(
        os.environ.get("AFTERMATH_GATEWAY_DB", "/data/gateway.sqlite3")
    )
    control = ThreadingHTTPServer(
        (
            os.environ.get("AFTERMATH_GATEWAY_CONTROL_HOST", "0.0.0.0"),
            int(os.environ.get("AFTERMATH_GATEWAY_CONTROL_PORT", "8081")),
        ),
        make_control_handler(state, audit),
    )
    threading.Thread(target=control.serve_forever, daemon=True).start()
    gateway = ThreadingHTTPServer(
        (
            os.environ.get("AFTERMATH_GATEWAY_HOST", "0.0.0.0"),
            int(os.environ.get("AFTERMATH_GATEWAY_PORT", "8080")),
        ),
        make_gateway_handler(
            upstream_url=os.environ.get(
                "AFTERMATH_GATEWAY_UPSTREAM",
                "http://frontend:8080",
            ),
            state=state,
            audit=audit,
            upstream_host_header=os.environ.get(
                "AFTERMATH_GATEWAY_UPSTREAM_HOST"
            ),
        ),
    )
    gateway.serve_forever()


if __name__ == "__main__":
    main()
