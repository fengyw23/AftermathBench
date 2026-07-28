# EnterpriseOps-Gym Integration Audit

Audited upstream revision:

```text
repository: https://github.com/ServiceNow/EnterpriseOps-Gym
revision: de22905d21a080b83bf4a54258afe4250ee2dd55
```

## What is publicly reusable

- SQL seed snapshots for the eight domains.
- Per-task MCP server URL, database snapshot, context headers, user prompt,
  selected tools, and SQL verifiers.
- HTTP database lifecycle endpoints:
  - `POST /api/seed-database`
  - `DELETE /api/delete-database`
- MCP `tools/list` and `tools/call` requests scoped by `x-database-id`.
- SQL verification through `POST /api/query`.
- Container images for each domain service.

The checked-out seed archive contains 93 entries and is approximately 14.5 MB.
Across all snapshots, seed inserts reference 149 distinct Hybrid-domain tables.
This is a union statistic: an individual Hybrid SQL snapshot references between
15 and 47 tables, with a maximum of 47. Dataset scale must therefore not be
reported as if every task operated on all 149 tables.

The public repository contains only 13 revised-task examples; the full task set
is loaded separately from Hugging Face.

## What is not present in the public repository

The server-side implementation of the 512 domain tools is not included in the
checked-out source tree. Those implementations run inside separately published
Docker images. Consequently, the public Python code does not expose:

- transaction begin/commit hooks;
- per-tool read/write sets;
- a hook between individual writes in a multi-record operation;
- an outbox or queue injection API;
- full database export after arbitrary tool calls.

Therefore, merely returning a timeout from the public MCP client would only
perturb the observation. It would not establish whether a real state transition
committed, partially committed, or entered an asynchronous queue.

## Safe integration design

AftermathBench will place a transparent transition-fault proxy in front of the
MCP service:

```text
agent → Aftermath fault proxy → EnterpriseOps MCP container → task database
```

The proxy may implement:

- `no_commit`: suppress the call;
- `full_commit_response_lost`: execute the real tool, verify its state delta,
  and suppress the response;
- `partial_commit`: only for operations whose component writes can be
  reproduced through public tools or explicit SQL fixtures;
- `asynchronous_commit_pending`: only when a real queue/job record exists or a
  benchmark-owned outbox adapter is used.

Every injected transition must be validated using task-relevant SQL queries
before the task is admitted. A label alone is insufficient.

## Use decision

EnterpriseOps-Gym remains the preferred source for enterprise schemas, tools,
policies, SQL snapshots, and workflow seeds. It is not, by itself, a native
partial-commit fault environment.

The pilot should first select tools whose writes can be reconstructed and
verified from public state. If a required transition cannot be verified or
decomposed, that workflow must be rejected rather than assigned a synthetic
partial-commit label.

The reproducible archive audit is available as:

```bash
python scripts/audit_enterprise_ops.py /path/to/gym_dbs.zip
```

## Implemented ITSM semantic slice

`itsm-major-incident-001` is the first workflow built from an audited
EnterpriseOps schema slice. It uses the upstream table names and relevant
columns for:

- `incident`, including impact, urgency, priority, assignment, service, parent,
  and work-note state;
- `incident_sla` and `sla_definition`;
- `configuration_item` and `incident_affected_cis`;
- `child_incident`;
- `knowledge` and `incident_knowledge`;
- `users`, `user_group`, and `user_group_member`;
- `notification`.

The successful prefix is replayed through six public benchmark tools. The
ambiguous escalation then has four real state-transition implementations:
no write, full multi-table commit with response loss, parent-only partial
commit, and a persisted queued job.

This slice runs in local SQLite and does not claim to execute the unpublished
EnterpriseOps server-side tool code. The benchmark-owned `escalation_job`,
`escalation_review`, `audit_event`, and `protocol_event` tables are explicitly
separated from the upstream-derived tables.
