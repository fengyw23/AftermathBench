from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def extract_delivery_key(
    payload: Any,
    headers: dict[str, str] | None = None,
) -> str:
    normalized_headers = {k.lower(): v for k, v in (headers or {}).items()}
    if value := normalized_headers.get("x-idempotency-key"):
        return value
    if isinstance(payload, dict):
        for key in ("idempotency_key", "payment_entry", "name"):
            if value := payload.get(key):
                return str(value)
        if isinstance(payload.get("doc"), dict) and payload["doc"].get("name"):
            return str(payload["doc"]["name"])
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DeliveryResult:
    key: str
    first_delivery: bool
    attempt_count: int
    body_sha256: str


class DeliveryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS delivery_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    delivery_key TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    body_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    headers_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS deliveries (
                    delivery_key TEXT PRIMARY KEY,
                    first_attempt_id INTEGER NOT NULL UNIQUE,
                    first_received_at TEXT NOT NULL,
                    body_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(first_attempt_id) REFERENCES delivery_attempts(id)
                );
                """
            )

    def record(
        self,
        payload: Any,
        headers: dict[str, str] | None = None,
    ) -> DeliveryResult:
        headers = headers or {}
        payload_json = _canonical_json(payload)
        body_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        delivery_key = extract_delivery_key(payload, headers)
        received_at = _utc_now()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO delivery_attempts(
                    delivery_key, received_at, body_sha256,
                    payload_json, headers_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    delivery_key,
                    received_at,
                    body_sha256,
                    payload_json,
                    _canonical_json(headers),
                ),
            )
            first_delivery = connection.execute(
                """
                INSERT OR IGNORE INTO deliveries(
                    delivery_key, first_attempt_id, first_received_at,
                    body_sha256, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    delivery_key,
                    cursor.lastrowid,
                    received_at,
                    body_sha256,
                    payload_json,
                ),
            ).rowcount == 1
            attempt_count = int(connection.execute(
                """
                SELECT COUNT(*) FROM delivery_attempts
                WHERE delivery_key = ?
                """,
                (delivery_key,),
            ).fetchone()[0])
        return DeliveryResult(
            key=delivery_key,
            first_delivery=first_delivery,
            attempt_count=attempt_count,
            body_sha256=body_sha256,
        )

    def get(self, key: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            delivery = connection.execute(
                "SELECT * FROM deliveries WHERE delivery_key = ?",
                (key,),
            ).fetchone()
            if delivery is None:
                return None
            attempts = connection.execute(
                """
                SELECT id, received_at, body_sha256, payload_json
                FROM delivery_attempts
                WHERE delivery_key = ?
                ORDER BY id
                """,
                (key,),
            ).fetchall()
        return {
            "key": key,
            "first_received_at": delivery["first_received_at"],
            "body_sha256": delivery["body_sha256"],
            "payload": json.loads(delivery["payload_json"]),
            "attempt_count": len(attempts),
            "attempts": [
                {
                    "id": row["id"],
                    "received_at": row["received_at"],
                    "body_sha256": row["body_sha256"],
                    "payload": json.loads(row["payload_json"]),
                }
                for row in attempts
            ],
        }

    def counts(self) -> dict[str, int]:
        with self._connection() as connection:
            deliveries = int(
                connection.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
            )
            attempts = int(
                connection.execute(
                    "SELECT COUNT(*) FROM delivery_attempts"
                ).fetchone()[0]
            )
        return {"unique_deliveries": deliveries, "attempts": attempts}

    def reset(self) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM deliveries")
            connection.execute("DELETE FROM delivery_attempts")


def _json_response(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: dict[str, Any],
) -> None:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def make_handler(store: DeliveryStore) -> type[BaseHTTPRequestHandler]:
    class RemittanceHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                _json_response(self, 200, {"ok": True, **store.counts()})
                return
            prefix = "/deliveries/"
            if parsed.path.startswith(prefix):
                key = unquote(parsed.path[len(prefix):])
                record = store.get(key)
                _json_response(
                    self,
                    200 if record else 404,
                    record or {"error": "not_found", "key": key},
                )
                return
            _json_response(self, 404, {"error": "not_found"})

        def do_POST(self) -> None:
            if urlparse(self.path).path not in {
                "/webhooks/remittance",
                "/webhooks/events",
            }:
                _json_response(self, 404, {"error": "not_found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _json_response(self, 400, {"error": "invalid_json"})
                return
            result = store.record(payload, dict(self.headers.items()))
            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "delivery_key": result.key,
                    "first_delivery": result.first_delivery,
                    "attempt_count": result.attempt_count,
                },
            )

        def do_DELETE(self) -> None:
            if urlparse(self.path).path != "/admin/reset":
                _json_response(self, 404, {"error": "not_found"})
                return
            store.reset()
            _json_response(self, 200, {"ok": True, **store.counts()})

    return RemittanceHandler


def main() -> None:
    database = os.environ.get(
        "AFTERMATH_REMITTANCE_DB",
        "/data/remittance.sqlite3",
    )
    host = os.environ.get("AFTERMATH_REMITTANCE_HOST", "0.0.0.0")
    port = int(os.environ.get("AFTERMATH_REMITTANCE_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), make_handler(DeliveryStore(database)))
    server.serve_forever()


if __name__ == "__main__":
    main()
