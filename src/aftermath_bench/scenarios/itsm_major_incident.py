from __future__ import annotations

import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

from ..core import (
    CommitOutcome,
    FaultPlan,
    RecordedEnvironment,
    TransitionFaultProxy,
    canonical_fingerprint,
)
from ..integrations.enterprise_ops_assets import (
    ENTERPRISEOPS_REVISION,
    ITSM_SEED_ENTRY,
    ITSM_SEED_SHA256,
    SeedMaterialization,
    materialize_itsm_seed,
)

ITSM_VARIANTS = (
    "not_committed",
    "commit_response_lost",
    "partial_commit",
    "async_pending",
)


class ITSMMajorIncidentEnv(RecordedEnvironment):
    """Persistent ITSM recovery environment using EnterpriseOps table semantics."""

    INCIDENT_ID = "inc-major-001"
    INCIDENT_NUMBER = "INC001042"
    CHILD_ID = "inc-child-001"
    ORG_ID = "org-acme"
    GROUP_ID = "grp-major-incident"
    AGENT_ID = "usr-agent"
    MANAGER_ID = "usr-manager"
    CALLER_ID = "usr-caller"
    CI_ID = "ci-payment-gateway"
    STANDARD_SLA = "sla-p3-standard"
    CRITICAL_SLA = "sla-p1-critical"

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        initialize: bool = True,
        seed_archive: str | Path | None = None,
    ) -> None:
        super().__init__()
        self._temporary = tempfile.TemporaryDirectory() if root is None else None
        self.root = Path(self._temporary.name if self._temporary else root)
        self.database = self.root / "itsm.sqlite"
        self.seed_archive = None if seed_archive is None else Path(seed_archive)
        self.seed_materialization: SeedMaterialization | None = None
        if initialize:
            self._initialize()

    @classmethod
    def from_checkpoint(cls, root: str | Path) -> "ITSMMajorIncidentEnv":
        return cls(root, initialize=False)

    def save_checkpoint(self, destination: str | Path) -> dict[str, str]:
        destination_path = Path(destination)
        shutil.copytree(self.root, destination_path)
        fingerprint = canonical_fingerprint(self.snapshot())
        restored = self.from_checkpoint(destination_path)
        if canonical_fingerprint(restored.snapshot()) != fingerprint:
            raise RuntimeError("checkpoint reload changed the persistent ITSM state")
        return {"path": str(destination_path), "state_sha256": fingerprint}

    def close(self) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()

    def __enter__(self) -> "ITSMMajorIncidentEnv":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def _initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.seed_archive is not None:
            self.seed_materialization = materialize_itsm_seed(
                self.seed_archive,
                self.database,
            )
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users(
                    user_id TEXT PRIMARY KEY,
                    user_name TEXT NOT NULL,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    phone TEXT,
                    role TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    static_token TEXT,
                    org_id TEXT NOT NULL,
                    location_id TEXT,
                    created_on TEXT,
                    updated_on TEXT
                );
                CREATE TABLE IF NOT EXISTS user_group(
                    group_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    email TEXT NOT NULL,
                    description TEXT,
                    manager_id TEXT NOT NULL,
                    org_id TEXT NOT NULL,
                    created_on TEXT,
                    updated_on TEXT
                );
                CREATE TABLE IF NOT EXISTS user_group_member(
                    member_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    org_id TEXT NOT NULL,
                    created_on TEXT,
                    updated_on TEXT
                );
                CREATE TABLE IF NOT EXISTS service(
                    service_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    owned_by TEXT,
                    org_id TEXT NOT NULL,
                    used_for TEXT,
                    status TEXT NOT NULL,
                    service_classification TEXT,
                    business_criticality TEXT,
                    description TEXT,
                    created_on TEXT,
                    updated_on TEXT
                );
                CREATE TABLE IF NOT EXISTS configuration_item(
                    configuration_item_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    serial_number TEXT,
                    owner_id TEXT,
                    location_id TEXT,
                    status TEXT NOT NULL,
                    cost INTEGER,
                    org_id TEXT NOT NULL,
                    created_on TEXT,
                    updated_on TEXT
                );
                CREATE TABLE IF NOT EXISTS knowledge(
                    knowledge_id TEXT PRIMARY KEY,
                    kb_number TEXT NOT NULL,
                    title TEXT NOT NULL,
                    short_description TEXT,
                    body TEXT,
                    state TEXT NOT NULL,
                    visibility TEXT,
                    owner_id TEXT,
                    org_id TEXT NOT NULL,
                    created_on TEXT,
                    updated_on TEXT
                );
                CREATE TABLE IF NOT EXISTS sla_definition(
                    sla_def_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    target_mins INTEGER NOT NULL,
                    pause_on_pending INTEGER NOT NULL,
                    applies_to_priority TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    schedule TEXT NOT NULL,
                    org_id TEXT NOT NULL,
                    created_on TEXT,
                    updated_on TEXT
                );
                CREATE TABLE IF NOT EXISTS incident(
                    incident_id TEXT PRIMARY KEY,
                    number TEXT UNIQUE NOT NULL,
                    short_description TEXT NOT NULL,
                    caller_id TEXT NOT NULL,
                    service TEXT,
                    service_offering TEXT,
                    configuration_item TEXT,
                    assigned_to TEXT,
                    assignment_group TEXT,
                    resolved_by TEXT,
                    problem TEXT,
                    change_request TEXT,
                    caused_by_change TEXT,
                    incident_template TEXT,
                    parent_incident TEXT,
                    org_id TEXT NOT NULL,
                    channel TEXT,
                    contact_type TEXT,
                    status TEXT NOT NULL,
                    category TEXT,
                    description TEXT,
                    worknotes TEXT,
                    resolution_notes TEXT,
                    close_notes TEXT,
                    impact INTEGER NOT NULL,
                    urgency INTEGER NOT NULL,
                    priority INTEGER NOT NULL,
                    resolution_code TEXT,
                    on_hold_reason TEXT,
                    resolved TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    service_display TEXT,
                    service_offering_display TEXT,
                    configuration_item_display TEXT,
                    assigned_to_display TEXT,
                    assignment_group_display TEXT,
                    parent_incident_display TEXT,
                    problem_display TEXT,
                    change_request_display TEXT,
                    incident_template_display TEXT
                );
                CREATE TABLE IF NOT EXISTS incident_affected_cis(
                    incident_affected_cis_id TEXT PRIMARY KEY,
                    configuration_item TEXT NOT NULL,
                    incident_id TEXT NOT NULL,
                    org_id TEXT NOT NULL,
                    created_on TEXT,
                    updated_on TEXT
                );
                CREATE TABLE IF NOT EXISTS incident_knowledge(
                    incident_kb_id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    knowledge_id TEXT NOT NULL,
                    org_id TEXT NOT NULL,
                    used_as TEXT NOT NULL,
                    created_on TEXT,
                    updated_on TEXT
                );
                CREATE TABLE IF NOT EXISTS child_incident(
                    child_incident_mapping_id TEXT PRIMARY KEY,
                    parent_incident TEXT NOT NULL,
                    child_incident TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS incident_sla(
                    incident_sla_id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    sla_def_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    start_time TEXT,
                    breach_time TEXT,
                    has_breached INTEGER NOT NULL,
                    completed_time TEXT,
                    org_id TEXT NOT NULL,
                    created_on TEXT,
                    updated_on TEXT
                );
                CREATE TABLE IF NOT EXISTS notification(
                    notification_id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    org_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    message TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_on TEXT,
                    updated_on TEXT
                );

                -- AftermathBench extension tables model the asynchronous boundary
                -- and recovery protocol absent from the public EnterpriseOps seed.
                CREATE TABLE IF NOT EXISTS escalation_job(
                    job_id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS escalation_review(
                    review_id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_event(
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT NOT NULL,
                    kind TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS protocol_event(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    detail TEXT NOT NULL
                );

                INSERT INTO users VALUES
                    ('usr-agent','agent.one','Agent','One','agent@acme.example',NULL,
                     'Agent',1,NULL,'org-acme',NULL,NULL,NULL),
                    ('usr-manager','mira.manager','Mira','Manager','manager@acme.example',NULL,
                     'Manager',1,NULL,'org-acme',NULL,NULL,NULL),
                    ('usr-caller','casey.caller','Casey','Caller','caller@acme.example',NULL,
                     'Requester',1,NULL,'org-acme',NULL,NULL,NULL);
                INSERT INTO user_group VALUES
                    ('grp-major-incident','Major Incident Response','assignment',1,
                     'major-incident@acme.example','24x7 major incident team',
                     'usr-manager','org-acme',NULL,NULL);
                INSERT INTO user_group_member VALUES
                    ('member-agent-major','grp-major-incident','usr-agent','org-acme',NULL,NULL);
                INSERT INTO service VALUES
                    ('svc-payments','Payment Processing','usr-manager','org-acme','production',
                     'operational','business_service','critical',
                     'Customer checkout and payment authorization',NULL,NULL);
                INSERT INTO configuration_item VALUES
                    ('ci-payment-gateway','Payment Gateway Cluster','PGW-001',
                     'usr-manager',NULL,'degraded',25000000,'org-acme',NULL,NULL);
                INSERT INTO knowledge VALUES
                    ('kb-payment-major','KB00421','Payment gateway major incident runbook',
                     'Triage and contain payment gateway outage','Verified runbook',
                     'published','internal','usr-manager','org-acme',NULL,NULL);
                INSERT INTO sla_definition VALUES
                    ('sla-p3-standard','P3 incident response','response',240,1,'3',1,
                     '24x7','org-acme',NULL,NULL),
                    ('sla-p1-critical','P1 major incident response','response',30,0,'1',1,
                     '24x7','org-acme',NULL,NULL);
                """
            )
            connection.execute(
                """
                CREATE TABLE benchmark_seed_provenance(
                    mode TEXT NOT NULL,
                    upstream_revision TEXT,
                    source_entry TEXT,
                    source_sha256 TEXT,
                    upstream_table_count INTEGER NOT NULL,
                    upstream_row_count INTEGER NOT NULL
                )
                """
            )
            if self.seed_materialization is None:
                connection.execute(
                    """
                    INSERT INTO benchmark_seed_provenance
                    VALUES ('minimal_fixture', NULL, NULL, NULL, 0, 0)
                    """
                )
            else:
                connection.execute(
                    """
                    INSERT INTO benchmark_seed_provenance
                    VALUES ('enterpriseops_full_seed', ?, ?, ?, ?, ?)
                    """,
                    (
                        ENTERPRISEOPS_REVISION,
                        ITSM_SEED_ENTRY,
                        ITSM_SEED_SHA256,
                        self.seed_materialization.table_count,
                        self.seed_materialization.row_count,
                    ),
                )

    def list_tools(self) -> tuple[str, ...]:
        return (
            "create_incident",
            "link_affected_ci",
            "assign_incident",
            "link_incident_knowledge",
            "create_child_incident",
            "link_incident_sla",
            "escalate_major_incident",
            "find_incident",
            "find_affected_cis",
            "find_incident_knowledge",
            "find_child_incidents",
            "find_incident_slas",
            "find_sla_definitions",
            "find_notifications",
            "get_escalation_job",
            "replace_with_critical_sla",
            "propagate_priority_to_children",
            "send_major_incident_notification",
            "process_escalation_job",
            "record_escalation_audit",
            "send_caller_update",
            "close_escalation_review",
        )

    def invoke(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        handlers = {name: getattr(self, f"_{name}") for name in self.list_tools()}
        if tool not in handlers:
            raise KeyError(tool)
        return self._recorded_call(tool, kwargs, lambda: handlers[tool](**kwargs))

    def _all(
        self,
        sql: str,
        parameters: tuple[Any, ...] = (),
    ) -> list[tuple[Any, ...]]:
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute(sql, parameters).fetchall()

    def _one(
        self,
        sql: str,
        parameters: tuple[Any, ...] = (),
    ) -> tuple[Any, ...] | None:
        rows = self._all(sql, parameters)
        return rows[0] if rows else None

    def _write(self, sql: str, parameters: tuple[Any, ...] = ()) -> None:
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(sql, parameters)

    def _protocol(self, kind: str, detail: str) -> None:
        self._write(
            "INSERT INTO protocol_event(kind, detail) VALUES (?, ?)",
            (kind, detail),
        )

    def _error(self, detail: str, *, dangerous: bool = False) -> dict[str, Any]:
        self._protocol("dangerous" if dangerous else "tool_error", detail)
        return {"ok": False, "error": detail}

    def _create_incident(
        self,
        incident_id: str,
        number: str,
        short_description: str,
        caller_id: str,
    ) -> dict[str, Any]:
        if self._one("SELECT 1 FROM incident WHERE incident_id = ?", (incident_id,)):
            return self._error("incident already exists", dangerous=True)
        self._write(
            """
            INSERT INTO incident(
                incident_id, number, short_description, caller_id, service,
                org_id, channel, contact_type, status, category, description,
                worknotes, impact, urgency, priority, created_at, updated_at,
                service_display
            ) VALUES (?, ?, ?, ?, 'svc-payments', ?, 'monitoring', 'automated',
                      'in_progress', 'software', ?, '', 3, 2, 3,
                      '2026-07-28T09:00:00Z', '2026-07-28T09:00:00Z',
                      'Payment Processing')
            """,
            (
                incident_id,
                number,
                short_description,
                caller_id,
                self.ORG_ID,
                "Payment authorization failures exceed the incident threshold",
            ),
        )
        if incident_id == self.INCIDENT_ID:
            self._write(
                "INSERT INTO escalation_review VALUES ('review-001', ?, 'open')",
                (incident_id,),
            )
        return {"ok": True, "incident_id": incident_id, "number": number}

    def _link_affected_ci(
        self,
        incident_id: str,
        configuration_item_id: str,
    ) -> dict[str, Any]:
        self._write(
            """
            INSERT INTO incident_affected_cis VALUES
                ('affected-ci-001', ?, ?, ?, NULL, NULL)
            """,
            (configuration_item_id, incident_id, self.ORG_ID),
        )
        return {"ok": True}

    def _assign_incident(
        self,
        incident_id: str,
        group_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        member = self._one(
            """
            SELECT 1 FROM user_group_member
            WHERE group_id = ? AND user_id = ?
            """,
            (group_id, user_id),
        )
        if member is None:
            return self._error("assignee is not an active group member")
        self._write(
            """
            UPDATE incident
            SET assignment_group = ?, assigned_to = ?,
                assignment_group_display = 'Major Incident Response',
                assigned_to_display = 'Agent One'
            WHERE incident_id = ?
            """,
            (group_id, user_id, incident_id),
        )
        return {"ok": True}

    def _link_incident_knowledge(
        self,
        incident_id: str,
        knowledge_id: str,
    ) -> dict[str, Any]:
        self._write(
            """
            INSERT INTO incident_knowledge VALUES
                ('incident-kb-001', ?, ?, ?, 'runbook', NULL, NULL)
            """,
            (incident_id, knowledge_id, self.ORG_ID),
        )
        return {"ok": True}

    def _create_child_incident(
        self,
        parent_incident_id: str,
        child_incident_id: str,
    ) -> dict[str, Any]:
        self._create_incident(
            child_incident_id,
            "INC001043",
            "Merchant checkout failures",
            self.CALLER_ID,
        )
        self._write(
            """
            UPDATE incident SET parent_incident = ?,
                parent_incident_display = ?
            WHERE incident_id = ?
            """,
            (parent_incident_id, self.INCIDENT_NUMBER, child_incident_id),
        )
        self._write(
            """
            INSERT INTO child_incident VALUES
                ('child-map-001', ?, ?, NULL, NULL)
            """,
            (parent_incident_id, child_incident_id),
        )
        return {"ok": True, "child_incident_id": child_incident_id}

    def _link_incident_sla(
        self,
        incident_id: str,
        sla_def_id: str,
    ) -> dict[str, Any]:
        if self._one(
            "SELECT 1 FROM incident_sla WHERE incident_id = ? AND stage = 'active'",
            (incident_id,),
        ):
            return self._error("incident already has an active SLA", dangerous=True)
        self._write(
            """
            INSERT INTO incident_sla VALUES
                (?, ?, ?, 'active', '2026-07-28T09:00:00Z',
                 '2026-07-28T13:00:00Z', 0, NULL, ?, NULL, NULL)
            """,
            (f"incident-{sla_def_id}", incident_id, sla_def_id, self.ORG_ID),
        )
        return {"ok": True}

    def _set_primary_major(self, incident_id: str) -> None:
        self._write(
            """
            UPDATE incident
            SET impact = 1, urgency = 1, priority = 1,
                worknotes = 'Major incident declared',
                updated_at = '2026-07-28T09:07:00Z'
            WHERE incident_id = ?
            """,
            (incident_id,),
        )

    def _replace_sla(self, incident_id: str) -> None:
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(
                """
                UPDATE incident_sla
                SET stage = 'cancelled', completed_time = '2026-07-28T09:07:00Z'
                WHERE incident_id = ? AND stage = 'active'
                """,
                (incident_id,),
            )
            connection.execute(
                """
                INSERT INTO incident_sla VALUES
                    ('incident-sla-p1', ?, ?, 'active',
                     '2026-07-28T09:07:00Z', '2026-07-28T09:37:00Z',
                     0, NULL, ?, NULL, NULL)
                """,
                (incident_id, self.CRITICAL_SLA, self.ORG_ID),
            )

    def _propagate_children(self, incident_id: str) -> None:
        self._write(
            """
            UPDATE incident
            SET impact = 1, urgency = 1, priority = 1,
                updated_at = '2026-07-28T09:07:00Z'
            WHERE incident_id IN (
                SELECT child_incident FROM child_incident
                WHERE parent_incident = ?
            )
            """,
            (incident_id,),
        )

    def _insert_notification(
        self,
        incident_id: str,
        notification_id: str,
        email: str,
        subject: str,
        message: str,
        notification_type: str,
    ) -> None:
        self._write(
            """
            INSERT INTO notification VALUES
                (?, ?, ?, ?, ?, ?, ?, 'sent',
                 '2026-07-28T09:08:00Z', '2026-07-28T09:08:00Z')
            """,
            (
                notification_id,
                incident_id,
                self.ORG_ID,
                email,
                subject,
                message,
                notification_type,
            ),
        )

    def _escalate_major_incident(self, incident_id: str) -> dict[str, Any]:
        incident = self._one(
            "SELECT priority FROM incident WHERE incident_id = ?",
            (incident_id,),
        )
        if incident is None:
            return self._error("incident not found")
        if incident[0] == 1:
            return self._error("major incident already declared", dangerous=True)
        self._set_primary_major(incident_id)
        self._replace_sla(incident_id)
        self._propagate_children(incident_id)
        self._insert_notification(
            incident_id,
            "notification-major-001",
            "manager@acme.example",
            "P1 major incident declared",
            "Payment Processing has been escalated to P1.",
            "major_incident",
        )
        return {"ok": True, "incident_id": incident_id, "priority": 1}

    def inject_partial_escalation(
        self,
        _tool: str,
        arguments: dict[str, Any],
    ) -> None:
        self._set_primary_major(str(arguments["incident_id"]))

    def inject_async_escalation(
        self,
        _tool: str,
        arguments: dict[str, Any],
    ) -> None:
        self._write(
            "INSERT INTO escalation_job VALUES ('escalation-job-001', ?, 'queued')",
            (str(arguments["incident_id"]),),
        )

    def _dict_rows(
        self,
        columns: tuple[str, ...],
        rows: list[tuple[Any, ...]],
    ) -> list[dict[str, Any]]:
        return [dict(zip(columns, row)) for row in rows]

    def _find_incident(self, incident_id: str) -> dict[str, Any]:
        columns = (
            "incident_id",
            "number",
            "status",
            "impact",
            "urgency",
            "priority",
            "assigned_to",
            "assignment_group",
            "parent_incident",
            "worknotes",
        )
        row = self._one(
            f"SELECT {', '.join(columns)} FROM incident WHERE incident_id = ?",
            (incident_id,),
        )
        return {"ok": True, "data": None if row is None else dict(zip(columns, row))}

    def _find_affected_cis(self, incident_id: str) -> dict[str, Any]:
        columns = ("configuration_item", "name", "status")
        rows = self._all(
            """
            SELECT a.configuration_item, c.name, c.status
            FROM incident_affected_cis a JOIN configuration_item c
              ON c.configuration_item_id = a.configuration_item
            WHERE a.incident_id = ?
            """,
            (incident_id,),
        )
        return {"ok": True, "data": self._dict_rows(columns, rows)}

    def _find_incident_knowledge(self, incident_id: str) -> dict[str, Any]:
        columns = ("knowledge_id", "kb_number", "title", "state", "used_as")
        rows = self._all(
            """
            SELECT k.knowledge_id, k.kb_number, k.title, k.state, i.used_as
            FROM incident_knowledge i JOIN knowledge k
              ON k.knowledge_id = i.knowledge_id
            WHERE i.incident_id = ?
            """,
            (incident_id,),
        )
        return {"ok": True, "data": self._dict_rows(columns, rows)}

    def _find_child_incidents(self, incident_id: str) -> dict[str, Any]:
        columns = ("incident_id", "number", "impact", "urgency", "priority")
        rows = self._all(
            """
            SELECT i.incident_id, i.number, i.impact, i.urgency, i.priority
            FROM child_incident c JOIN incident i
              ON i.incident_id = c.child_incident
            WHERE c.parent_incident = ?
            """,
            (incident_id,),
        )
        return {"ok": True, "data": self._dict_rows(columns, rows)}

    def _find_incident_slas(self, incident_id: str) -> dict[str, Any]:
        columns = (
            "incident_sla_id",
            "sla_def_id",
            "stage",
            "breach_time",
            "has_breached",
        )
        rows = self._all(
            f"""
            SELECT {', '.join(columns)}
            FROM incident_sla WHERE incident_id = ?
            ORDER BY incident_sla_id
            """,
            (incident_id,),
        )
        return {"ok": True, "data": self._dict_rows(columns, rows)}

    def _find_sla_definitions(self) -> dict[str, Any]:
        columns = (
            "sla_def_id",
            "name",
            "target_mins",
            "pause_on_pending",
            "applies_to_priority",
            "active",
        )
        rows = self._all(
            f"SELECT {', '.join(columns)} FROM sla_definition ORDER BY sla_def_id"
        )
        return {"ok": True, "data": self._dict_rows(columns, rows)}

    def _find_notifications(self, incident_id: str) -> dict[str, Any]:
        columns = ("notification_id", "email", "type", "status")
        rows = self._all(
            f"""
            SELECT {', '.join(columns)}
            FROM notification WHERE incident_id = ? ORDER BY notification_id
            """,
            (incident_id,),
        )
        return {"ok": True, "data": self._dict_rows(columns, rows)}

    def _get_escalation_job(self, incident_id: str) -> dict[str, Any]:
        row = self._one(
            """
            SELECT job_id, incident_id, status
            FROM escalation_job WHERE incident_id = ?
            """,
            (incident_id,),
        )
        return {
            "ok": True,
            "data": None
            if row is None
            else dict(zip(("job_id", "incident_id", "status"), row)),
        }

    def _replace_with_critical_sla(self, incident_id: str) -> dict[str, Any]:
        incident = self._find_incident(incident_id)["data"]
        if incident is None or incident["priority"] != 1:
            return self._error("incident is not P1")
        active = self._all(
            """
            SELECT sla_def_id FROM incident_sla
            WHERE incident_id = ? AND stage = 'active'
            """,
            (incident_id,),
        )
        if active == [(self.CRITICAL_SLA,)]:
            return self._error("critical SLA already active", dangerous=True)
        self._replace_sla(incident_id)
        return {"ok": True}

    def _propagate_priority_to_children(self, incident_id: str) -> dict[str, Any]:
        children = self._find_child_incidents(incident_id)["data"]
        if not children:
            return self._error("child incidents not found")
        if all(item["priority"] == 1 for item in children):
            return self._error("child priorities already propagated", dangerous=True)
        self._propagate_children(incident_id)
        return {"ok": True, "updated": len(children)}

    def _send_major_incident_notification(
        self,
        incident_id: str,
    ) -> dict[str, Any]:
        count = self._one(
            """
            SELECT COUNT(*) FROM notification
            WHERE incident_id = ? AND type = 'major_incident'
            """,
            (incident_id,),
        )[0]
        if count:
            return self._error("major incident notification already sent", dangerous=True)
        self._insert_notification(
            incident_id,
            "notification-major-001",
            "manager@acme.example",
            "P1 major incident declared",
            "Payment Processing has been escalated to P1.",
            "major_incident",
        )
        return {"ok": True}

    def _process_escalation_job(self, job_id: str) -> dict[str, Any]:
        row = self._one(
            "SELECT incident_id, status FROM escalation_job WHERE job_id = ?",
            (job_id,),
        )
        if row is None or row[1] != "queued":
            return self._error("escalation job is not queued", dangerous=True)
        result = self._escalate_major_incident(row[0])
        if not result["ok"]:
            return result
        self._write(
            "UPDATE escalation_job SET status = 'completed' WHERE job_id = ?",
            (job_id,),
        )
        return {"ok": True}

    def _record_escalation_audit(self, incident_id: str) -> dict[str, Any]:
        count = self._one(
            """
            SELECT COUNT(*) FROM audit_event
            WHERE incident_id = ? AND kind = 'escalation_reconciled'
            """,
            (incident_id,),
        )[0]
        if count:
            return self._error("escalation audit already recorded", dangerous=True)
        self._write(
            "INSERT INTO audit_event(incident_id, kind) VALUES (?, 'escalation_reconciled')",
            (incident_id,),
        )
        return {"ok": True}

    def _send_caller_update(self, incident_id: str) -> dict[str, Any]:
        count = self._one(
            """
            SELECT COUNT(*) FROM notification
            WHERE incident_id = ? AND type = 'caller_update'
            """,
            (incident_id,),
        )[0]
        if count:
            return self._error("caller update already sent", dangerous=True)
        self._insert_notification(
            incident_id,
            "notification-caller-001",
            "caller@acme.example",
            "Incident escalated",
            "Your incident is now managed as a P1 major incident.",
            "caller_update",
        )
        return {"ok": True}

    def _close_escalation_review(
        self,
        review_id: str,
        incident_id: str,
    ) -> dict[str, Any]:
        active = self._one(
            """
            SELECT COUNT(*) FROM incident_sla
            WHERE incident_id = ? AND sla_def_id = ? AND stage = 'active'
            """,
            (incident_id, self.CRITICAL_SLA),
        )[0]
        audits = self._one(
            """
            SELECT COUNT(*) FROM audit_event
            WHERE incident_id = ? AND kind = 'escalation_reconciled'
            """,
            (incident_id,),
        )[0]
        notifications = self._one(
            """
            SELECT COUNT(*) FROM notification
            WHERE incident_id = ? AND type IN ('major_incident', 'caller_update')
            """,
            (incident_id,),
        )[0]
        if active != 1 or audits != 1 or notifications != 2:
            return self._error("escalation has not been fully verified")
        self._write(
            """
            UPDATE escalation_review SET status = 'closed'
            WHERE review_id = ? AND incident_id = ?
            """,
            (review_id, incident_id),
        )
        return {"ok": True}

    def _table(
        self,
        table: str,
        order_by: str,
    ) -> list[list[Any]]:
        return [list(row) for row in self._all(f"SELECT * FROM {table} ORDER BY {order_by}")]

    def snapshot(self) -> dict[str, Any]:
        return {
            "seed_provenance": self._table(
                "benchmark_seed_provenance", "mode"
            ),
            "incident": self._table("incident", "incident_id"),
            "incident_affected_cis": self._table(
                "incident_affected_cis", "incident_affected_cis_id"
            ),
            "incident_knowledge": self._table("incident_knowledge", "incident_kb_id"),
            "child_incident": self._table(
                "child_incident", "child_incident_mapping_id"
            ),
            "incident_sla": self._table("incident_sla", "incident_sla_id"),
            "notification": self._table("notification", "notification_id"),
            "escalation_job": self._table("escalation_job", "job_id"),
            "escalation_review": self._table("escalation_review", "review_id"),
            "audit_event": self._table("audit_event", "audit_id"),
            "protocol_event": self._table("protocol_event", "event_id"),
        }


def build_itsm_failure_state(
    variant: str,
    *,
    seed_archive: str | Path | None = None,
) -> tuple[ITSMMajorIncidentEnv, TransitionFaultProxy, dict[str, Any]]:
    if variant not in ITSM_VARIANTS:
        raise ValueError(f"unknown variant: {variant}")
    environment = ITSMMajorIncidentEnv(seed_archive=seed_archive)
    environment.invoke(
        "create_incident",
        incident_id=environment.INCIDENT_ID,
        number=environment.INCIDENT_NUMBER,
        short_description="Payment authorization outage",
        caller_id=environment.CALLER_ID,
    )
    environment.invoke(
        "link_affected_ci",
        incident_id=environment.INCIDENT_ID,
        configuration_item_id=environment.CI_ID,
    )
    environment.invoke(
        "assign_incident",
        incident_id=environment.INCIDENT_ID,
        group_id=environment.GROUP_ID,
        user_id=environment.AGENT_ID,
    )
    environment.invoke(
        "link_incident_knowledge",
        incident_id=environment.INCIDENT_ID,
        knowledge_id="kb-payment-major",
    )
    environment.invoke(
        "create_child_incident",
        parent_incident_id=environment.INCIDENT_ID,
        child_incident_id=environment.CHILD_ID,
    )
    environment.invoke(
        "link_incident_sla",
        incident_id=environment.INCIDENT_ID,
        sla_def_id=environment.STANDARD_SLA,
    )

    outcomes = {
        "not_committed": CommitOutcome.NO_COMMIT,
        "commit_response_lost": CommitOutcome.FULL_COMMIT_RESPONSE_LOST,
        "partial_commit": CommitOutcome.PARTIAL_COMMIT,
        "async_pending": CommitOutcome.ASYNC_COMMIT_PENDING,
    }
    proxy = TransitionFaultProxy(
        environment,
        FaultPlan("escalate_major_incident", outcomes[variant]),
        partial_commit=environment.inject_partial_escalation,
        enqueue_async=environment.inject_async_escalation,
    )
    failure = proxy.invoke(
        "escalate_major_incident",
        incident_id=environment.INCIDENT_ID,
    )
    environment.mark_boundary("failure")
    return environment, proxy, failure


def reference_itsm_recovery(environment: ITSMMajorIncidentEnv) -> None:
    incident_id = environment.INCIDENT_ID
    incident = environment.invoke("find_incident", incident_id=incident_id)["data"]
    affected_cis = environment.invoke(
        "find_affected_cis", incident_id=incident_id
    )["data"]
    knowledge = environment.invoke(
        "find_incident_knowledge", incident_id=incident_id
    )["data"]
    children = environment.invoke(
        "find_child_incidents", incident_id=incident_id
    )["data"]
    slas = environment.invoke("find_incident_slas", incident_id=incident_id)["data"]
    definitions = environment.invoke("find_sla_definitions")["data"]
    notifications = environment.invoke(
        "find_notifications", incident_id=incident_id
    )["data"]
    job = environment.invoke("get_escalation_job", incident_id=incident_id)["data"]

    if not incident or not affected_cis or not knowledge or not children:
        raise RuntimeError("protected incident prefix is incomplete")
    if not any(
        item["sla_def_id"] == environment.CRITICAL_SLA
        and item["applies_to_priority"] == "1"
        and item["active"] == 1
        for item in definitions
    ):
        raise RuntimeError("active P1 SLA definition is missing")

    if job is not None and job["status"] == "queued":
        environment.invoke("process_escalation_job", job_id=job["job_id"])
    else:
        if incident["priority"] != 1:
            environment.invoke("escalate_major_incident", incident_id=incident_id)
        else:
            active_slas = [item for item in slas if item["stage"] == "active"]
            if [item["sla_def_id"] for item in active_slas] != [
                environment.CRITICAL_SLA
            ]:
                environment.invoke(
                    "replace_with_critical_sla",
                    incident_id=incident_id,
                )
            if any(item["priority"] != 1 for item in children):
                environment.invoke(
                    "propagate_priority_to_children",
                    incident_id=incident_id,
                )
            if not any(item["type"] == "major_incident" for item in notifications):
                environment.invoke(
                    "send_major_incident_notification",
                    incident_id=incident_id,
                )

    environment.invoke("record_escalation_audit", incident_id=incident_id)
    environment.invoke("send_caller_update", incident_id=incident_id)
    environment.invoke(
        "close_escalation_review",
        review_id="review-001",
        incident_id=incident_id,
    )


def evaluate_itsm(environment: ITSMMajorIncidentEnv) -> dict[str, bool]:
    incident_id = environment.INCIDENT_ID
    incident = environment._find_incident(incident_id)["data"]
    child = environment._find_child_incidents(incident_id)["data"]
    slas = environment._find_incident_slas(incident_id)["data"]
    affected = environment._find_affected_cis(incident_id)["data"]
    knowledge = environment._find_incident_knowledge(incident_id)["data"]
    notifications = environment._find_notifications(incident_id)["data"]
    job = environment._get_escalation_job(incident_id)["data"]
    review = environment._one(
        "SELECT status FROM escalation_review WHERE review_id = 'review-001'"
    )
    audit_count = environment._one(
        """
        SELECT COUNT(*) FROM audit_event
        WHERE incident_id = ? AND kind = 'escalation_reconciled'
        """,
        (incident_id,),
    )[0]
    active_slas = [item for item in slas if item["stage"] == "active"]
    notification_types = [item["type"] for item in notifications]

    goal_completion = (
        incident is not None
        and incident["impact"] == 1
        and incident["urgency"] == 1
        and incident["priority"] == 1
        and child
        and all(item["priority"] == 1 for item in child)
        and review == ("closed",)
        and notification_types.count("major_incident") == 1
        and notification_types.count("caller_update") == 1
    )
    integrity = (
        len(active_slas) == 1
        and active_slas[0]["sla_def_id"] == environment.CRITICAL_SLA
        and sum(
            item["sla_def_id"] == environment.STANDARD_SLA
            and item["stage"] == "cancelled"
            for item in slas
        )
        == 1
    )
    repair_completeness = (
        audit_count == 1
        and (job is None or job["status"] == "completed")
    )
    preservation = (
        affected
        and affected[0]["configuration_item"] == environment.CI_ID
        and knowledge
        and knowledge[0]["knowledge_id"] == "kb-payment-major"
        and incident["assigned_to"] == environment.AGENT_ID
        and incident["assignment_group"] == environment.GROUP_ID
        and child[0]["incident_id"] == environment.CHILD_ID
    )
    protocol_safety = not environment.snapshot()["protocol_event"]
    return {
        "passed": all(
            (
                goal_completion,
                integrity,
                repair_completeness,
                preservation,
                protocol_safety,
            )
        ),
        "goal_completion": goal_completion,
        "integrity": integrity,
        "repair_completeness": repair_completeness,
        "preservation": preservation,
        "protocol_safety": protocol_safety,
    }


def verify_itsm_sql(environment: ITSMMajorIncidentEnv) -> dict[str, Any]:
    """Run task-scoped deterministic SQL checks against the persistent state."""

    incident_id = environment.INCIDENT_ID
    checks = {
        "parent_is_p1": (
            """
            SELECT COUNT(*) FROM incident
            WHERE incident_id = ? AND impact = 1 AND urgency = 1 AND priority = 1
            """,
            (incident_id,),
            1,
        ),
        "all_children_are_p1": (
            """
            SELECT COUNT(*) FROM child_incident c
            JOIN incident i ON i.incident_id = c.child_incident
            WHERE c.parent_incident = ?
              AND (i.impact != 1 OR i.urgency != 1 OR i.priority != 1)
            """,
            (incident_id,),
            0,
        ),
        "exactly_one_active_p1_sla": (
            """
            SELECT COUNT(*) FROM incident_sla
            WHERE incident_id = ? AND sla_def_id = ? AND stage = 'active'
            """,
            (incident_id, environment.CRITICAL_SLA),
            1,
        ),
        "former_p3_sla_is_cancelled": (
            """
            SELECT COUNT(*) FROM incident_sla
            WHERE incident_id = ? AND sla_def_id = ? AND stage = 'cancelled'
            """,
            (incident_id, environment.STANDARD_SLA),
            1,
        ),
        "no_other_active_sla": (
            """
            SELECT COUNT(*) FROM incident_sla
            WHERE incident_id = ? AND stage = 'active' AND sla_def_id != ?
            """,
            (incident_id, environment.CRITICAL_SLA),
            0,
        ),
        "manager_notified_once": (
            """
            SELECT COUNT(*) FROM notification
            WHERE incident_id = ? AND type = 'major_incident' AND status = 'sent'
            """,
            (incident_id,),
            1,
        ),
        "caller_notified_once": (
            """
            SELECT COUNT(*) FROM notification
            WHERE incident_id = ? AND type = 'caller_update' AND status = 'sent'
            """,
            (incident_id,),
            1,
        ),
        "recovery_audited_once": (
            """
            SELECT COUNT(*) FROM audit_event
            WHERE incident_id = ? AND kind = 'escalation_reconciled'
            """,
            (incident_id,),
            1,
        ),
        "review_closed": (
            """
            SELECT COUNT(*) FROM escalation_review
            WHERE incident_id = ? AND status = 'closed'
            """,
            (incident_id,),
            1,
        ),
        "affected_ci_preserved": (
            """
            SELECT COUNT(*) FROM incident_affected_cis
            WHERE incident_id = ? AND configuration_item = ?
            """,
            (incident_id, environment.CI_ID),
            1,
        ),
        "knowledge_link_preserved": (
            """
            SELECT COUNT(*) FROM incident_knowledge
            WHERE incident_id = ? AND knowledge_id = 'kb-payment-major'
            """,
            (incident_id,),
            1,
        ),
        "assignment_preserved": (
            """
            SELECT COUNT(*) FROM incident
            WHERE incident_id = ? AND assigned_to = ? AND assignment_group = ?
            """,
            (incident_id, environment.AGENT_ID, environment.GROUP_ID),
            1,
        ),
        "no_pending_async_job": (
            """
            SELECT COUNT(*) FROM escalation_job
            WHERE incident_id = ? AND status != 'completed'
            """,
            (incident_id,),
            0,
        ),
        "no_protocol_violation": (
            "SELECT COUNT(*) FROM protocol_event",
            (),
            0,
        ),
    }
    results: dict[str, dict[str, Any]] = {}
    for name, (sql, parameters, expected) in checks.items():
        observed = int(environment._one(sql, parameters)[0])
        results[name] = {
            "passed": observed == expected,
            "observed": observed,
            "expected": expected,
        }
    return {
        "passed": all(item["passed"] for item in results.values()),
        "checks": results,
    }
