from __future__ import annotations

import json
import os
import sqlite3
import urllib.parse
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


class DeploymentStore:
    """Small persistent deployment target driven by native Actions jobs."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS migrations (
                    migration_id TEXT PRIMARY KEY,
                    version TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    version TEXT PRIMARY KEY,
                    digest TEXT NOT NULL,
                    source_commit TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS deployments (
                    environment TEXT PRIMARY KEY,
                    desired_version TEXT NOT NULL,
                    artifact_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rollout_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    environment TEXT NOT NULL,
                    version TEXT NOT NULL,
                    artifact_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS replicas (
                    environment TEXT NOT NULL,
                    replica TEXT NOT NULL,
                    version TEXT NOT NULL,
                    artifact_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    PRIMARY KEY(environment, replica)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_key TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL
                );
                """
            )

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

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def apply_migration(self, payload: dict[str, Any]) -> dict[str, Any]:
        migration_id = str(payload["migration_id"])
        version = str(payload["version"])
        schema_hash = str(payload["schema_hash"])
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT * FROM migrations WHERE migration_id = ?",
                (migration_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["version"] != version
                    or existing["schema_hash"] != schema_hash
                ):
                    raise ValueError("migration identity conflicts with prior application")
                connection.execute(
                    "UPDATE migrations SET attempt_count = attempt_count + 1 "
                    "WHERE migration_id = ?",
                    (migration_id,),
                )
                first_application = False
            else:
                connection.execute(
                    "INSERT INTO migrations VALUES (?, ?, ?, ?, 1)",
                    (migration_id, version, schema_hash, _now()),
                )
                first_application = True
            row = connection.execute(
                "SELECT * FROM migrations WHERE migration_id = ?",
                (migration_id,),
            ).fetchone()
        return {**dict(row), "first_application": first_application}

    def register_artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        version = str(payload["version"])
        digest = str(payload["digest"])
        source_commit = str(payload["source_commit"])
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT * FROM artifacts WHERE version = ?", (version,)
            ).fetchone()
            if existing is not None:
                if (
                    existing["digest"] != digest
                    or existing["source_commit"] != source_commit
                ):
                    raise ValueError("artifact version conflicts with prior registration")
                connection.execute(
                    "UPDATE artifacts SET attempt_count = attempt_count + 1 "
                    "WHERE version = ?",
                    (version,),
                )
                first_registration = False
            else:
                connection.execute(
                    "INSERT INTO artifacts VALUES (?, ?, ?, ?, 1)",
                    (version, digest, source_commit, _now()),
                )
                first_registration = True
            row = connection.execute(
                "SELECT * FROM artifacts WHERE version = ?", (version,)
            ).fetchone()
        return {**dict(row), "first_registration": first_registration}

    def request_deployment(self, payload: dict[str, Any]) -> dict[str, Any]:
        environment = str(payload["environment"])
        version = str(payload["version"])
        migration_id = str(payload["migration_id"])
        with self._connection() as connection:
            migration = connection.execute(
                "SELECT * FROM migrations WHERE migration_id = ? AND version = ?",
                (migration_id, version),
            ).fetchone()
            artifact = connection.execute(
                "SELECT * FROM artifacts WHERE version = ?", (version,)
            ).fetchone()
            if migration is None or artifact is None:
                raise ValueError("deployment prerequisites are incomplete")
            active = connection.execute(
                "SELECT * FROM rollout_jobs WHERE environment = ? AND version = ? "
                "AND status IN ('queued', 'running') ORDER BY id DESC LIMIT 1",
                (environment, version),
            ).fetchone()
            deployment = connection.execute(
                "SELECT * FROM deployments WHERE environment = ?", (environment,)
            ).fetchone()
            if active is not None:
                return {**dict(active), "created": False}
            if (
                deployment is not None
                and deployment["desired_version"] == version
                and deployment["status"] == "deployed"
            ):
                completed = connection.execute(
                    "SELECT * FROM rollout_jobs WHERE environment = ? AND version = ? "
                    "AND status = 'completed' ORDER BY id DESC LIMIT 1",
                    (environment, version),
                ).fetchone()
                return {**dict(completed), "created": False}
            generation = 1 if deployment is None else int(deployment["generation"]) + 1
            connection.execute(
                "INSERT INTO deployments VALUES (?, ?, ?, 'pending', ?, ? ) "
                "ON CONFLICT(environment) DO UPDATE SET "
                "desired_version=excluded.desired_version, "
                "artifact_digest=excluded.artifact_digest, status='pending', "
                "generation=excluded.generation, updated_at=excluded.updated_at",
                (environment, version, artifact["digest"], generation, _now()),
            )
            cursor = connection.execute(
                "INSERT INTO rollout_jobs(environment, version, artifact_digest, "
                "status, created_at) VALUES (?, ?, ?, 'queued', ?)",
                (environment, version, artifact["digest"], _now()),
            )
            job = connection.execute(
                "SELECT * FROM rollout_jobs WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return {**dict(job), "created": True}

    def request_artifact_deployment(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Queue a deployment whose only prerequisite is an approved artifact.

        Migration deployments deliberately require a schema migration. Signed
        artifact promotions are a separate recovery family and must not invent
        one merely to reuse that endpoint.
        """

        environment = str(payload["environment"])
        version = str(payload["version"])
        digest = str(payload["artifact_digest"])
        with self._connection() as connection:
            artifact = connection.execute(
                "SELECT * FROM artifacts WHERE version = ?", (version,)
            ).fetchone()
            if artifact is None or artifact["digest"] != digest:
                raise ValueError("approved artifact prerequisite is incomplete")
            active = connection.execute(
                "SELECT * FROM rollout_jobs WHERE environment = ? AND version = ? "
                "AND status IN ('queued', 'running') ORDER BY id DESC LIMIT 1",
                (environment, version),
            ).fetchone()
            deployment = connection.execute(
                "SELECT * FROM deployments WHERE environment = ?", (environment,)
            ).fetchone()
            if active is not None:
                return {**dict(active), "created": False}
            if (
                deployment is not None
                and deployment["desired_version"] == version
                and deployment["artifact_digest"] == digest
                and deployment["status"] == "deployed"
            ):
                completed = connection.execute(
                    "SELECT * FROM rollout_jobs WHERE environment = ? AND version = ? "
                    "AND status = 'completed' ORDER BY id DESC LIMIT 1",
                    (environment, version),
                ).fetchone()
                if completed is None:
                    raise ValueError("deployed state has no completed rollout job")
                return {**dict(completed), "created": False}
            generation = 1 if deployment is None else int(deployment["generation"]) + 1
            connection.execute(
                "INSERT INTO deployments VALUES (?, ?, ?, 'pending', ?, ?) "
                "ON CONFLICT(environment) DO UPDATE SET "
                "desired_version=excluded.desired_version, "
                "artifact_digest=excluded.artifact_digest, status='pending', "
                "generation=excluded.generation, updated_at=excluded.updated_at",
                (environment, version, digest, generation, _now()),
            )
            cursor = connection.execute(
                "INSERT INTO rollout_jobs(environment, version, artifact_digest, "
                "status, created_at) VALUES (?, ?, ?, 'queued', ?)",
                (environment, version, digest, _now()),
            )
            job = connection.execute(
                "SELECT * FROM rollout_jobs WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return {**dict(job), "created": True}

    def run_workers(self) -> dict[str, Any]:
        completed: list[int] = []
        with self._connection() as connection:
            jobs = connection.execute(
                "SELECT * FROM rollout_jobs WHERE status = 'queued' ORDER BY id"
            ).fetchall()
            for job in jobs:
                connection.execute(
                    "UPDATE rollout_jobs SET status = 'running' WHERE id = ?",
                    (job["id"],),
                )
                for replica in ("replica-a", "replica-b"):
                    connection.execute(
                        "INSERT INTO replicas VALUES (?, ?, ?, ?, 'ready') "
                        "ON CONFLICT(environment, replica) DO UPDATE SET "
                        "version=excluded.version, "
                        "artifact_digest=excluded.artifact_digest, status='ready'",
                        (
                            job["environment"],
                            replica,
                            job["version"],
                            job["artifact_digest"],
                        ),
                    )
                completed_at = _now()
                connection.execute(
                    "UPDATE rollout_jobs SET status='completed', completed_at=? "
                    "WHERE id=?",
                    (completed_at, job["id"]),
                )
                connection.execute(
                    "UPDATE deployments SET status='deployed', updated_at=? "
                    "WHERE environment=?",
                    (completed_at, job["environment"]),
                )
                completed.append(int(job["id"]))
        return {"completed_job_ids": completed}

    def record_audit(self, payload: dict[str, Any]) -> dict[str, Any]:
        event_key = str(payload["event_key"])
        event_type = str(payload["event_type"])
        encoded = json.dumps(payload.get("payload", {}), sort_keys=True)
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT * FROM audit_events WHERE event_key = ?", (event_key,)
            ).fetchone()
            if existing is not None:
                if existing["event_type"] != event_type or existing["payload"] != encoded:
                    raise ValueError("audit key conflicts with prior event")
                connection.execute(
                    "UPDATE audit_events SET attempt_count = attempt_count + 1 "
                    "WHERE event_key = ?",
                    (event_key,),
                )
                first_record = False
            else:
                connection.execute(
                    "INSERT INTO audit_events VALUES (?, ?, ?, ?, 1)",
                    (event_key, event_type, encoded, _now()),
                )
                first_record = True
            row = connection.execute(
                "SELECT * FROM audit_events WHERE event_key = ?", (event_key,)
            ).fetchone()
        return {**dict(row), "payload": json.loads(row["payload"]), "first_record": first_record}

    def delete_artifact(self, version: str) -> dict[str, Any]:
        """Fault-injection administration for a lost registry record.

        The public agent API does not expose this operation.  Native boundary
        construction uses it to represent an independently missing registry
        effect while preserving a deployment that already consumed the digest.
        """

        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM artifacts WHERE version = ?", (version,)
            ).fetchone()
            if row is None:
                return {"version": version, "deleted": False}
            connection.execute("DELETE FROM artifacts WHERE version = ?", (version,))
        return {"version": version, "deleted": True}

    def state(self) -> dict[str, Any]:
        with self._connection() as connection:
            result = {}
            for table in (
                "migrations",
                "artifacts",
                "deployments",
                "rollout_jobs",
                "replicas",
                "audit_events",
            ):
                rows = connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                result[table] = [dict(row) for row in rows]
        for event in result["audit_events"]:
            event["payload"] = json.loads(event["payload"])
        return result

    def reset(self) -> None:
        with self._connection() as connection:
            for table in (
                "audit_events",
                "replicas",
                "rollout_jobs",
                "deployments",
                "artifacts",
                "migrations",
            ):
                connection.execute(f"DELETE FROM {table}")


def make_handler(store: DeploymentStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _respond(self, status: int, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _payload(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            value = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(value, dict):
                raise TypeError("request body must be an object")
            return value

        def do_GET(self) -> None:
            if self.path == "/health":
                self._respond(200, {"ok": True})
            elif self.path == "/state":
                self._respond(200, store.state())
            else:
                self._respond(404, {"error": "not_found"})

        def do_POST(self) -> None:
            try:
                operations = {
                    "/migrations": store.apply_migration,
                    "/artifacts": store.register_artifact,
                    "/deployments": store.request_deployment,
                    "/artifact-deployments": store.request_artifact_deployment,
                    "/workers/run": lambda _payload: store.run_workers(),
                    "/audit-events": store.record_audit,
                }
                operation = operations.get(self.path)
                if operation is None:
                    self._respond(404, {"error": "not_found"})
                    return
                self._respond(200, operation(self._payload()))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                self._respond(409, {"error": str(error)})

        def do_DELETE(self) -> None:
            if self.path == "/admin/reset":
                store.reset()
                self._respond(200, {"ok": True})
                return
            prefix = "/admin/artifacts/"
            if self.path.startswith(prefix):
                version = urllib.parse.unquote(self.path[len(prefix) :])
                if not version:
                    self._respond(400, {"error": "version_required"})
                    return
                self._respond(200, store.delete_artifact(version))
                return
            self._respond(404, {"error": "not_found"})

    return Handler


def main() -> None:
    store = DeploymentStore(
        os.environ.get(
            "AFTERMATH_DEPLOYMENT_DB", "/data/deployment-target.sqlite3"
        )
    )
    server = ThreadingHTTPServer(
        (
            os.environ.get("AFTERMATH_DEPLOYMENT_HOST", "0.0.0.0"),
            int(os.environ.get("AFTERMATH_DEPLOYMENT_PORT", "8080")),
        ),
        make_handler(store),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
