# Pilot Implementation Status

## Executable legacy prototypes

| Workflow | Prefix provenance | Persistent state carriers | Matched faults | Deterministic evaluation |
|---|---|---|---|---|
| Enterprise employee transfer | Six public environment write tools | Prototype enterprise state store | no commit, response lost, partial, async | Yes |
| ITSM major-incident escalation | Six public environment write tools | Pinned 24-table, 241-row EnterpriseOps seed plus task records and extensions | no commit, response lost, partial, async | Yes |
| Release and database migration | Six public environment write tools | Real Git repository, two SQLite databases, registry file | no commit, response lost, partial, async | Yes |

These workflows begin from a clean state, replay the successful prefix, inject
an ambiguous failed transition, and mark a fixed recovery boundary. They remain
available at tag `v0.2.0` for regression and idea validation.

## Status correction

The employee-transfer workflow uses AftermathBench's own state store. The ITSM
workflow uses public EnterpriseOps-Gym seed tables and relations, but runs
against inferred local SQLite tools. The upstream repository does not publish
the domain server implementation and native transaction logic used by its MCP
images.

The ITSM workflow is therefore a **legacy concept prototype**, not a native
EnterpriseOps integration, and will not enter the final benchmark leaderboard.
Its model adapters, full trajectories, state fingerprints, and fourteen SQL
checks remain useful for regression.

The release workflow has independent persistent state carriers, but its
deployment control plane remains local rather than a fully open production
service. It is also retained as a prototype.

## Native-runtime migration

ERPNext/Frappe is now the primary enterprise substrate. Source audit confirmed
public document schemas, business logic, SQL commit/rollback, post-commit
callbacks, webhook queuing, and background jobs. The first
procurement-to-payment scenario contains seven successful prefix writes and
four matched, source-supported failure states.

This scenario is not yet executable. It remains blocked from execution
admission until the pinned stack is built from source, deterministic reset is
verified, every fault is replayed, and terminal checks pass.

## Next enterprise implementation

1. Build pinned ERPNext/Frappe/MariaDB/Redis services from source.
2. Implement the procurement prefix exclusively through public document APIs.
3. Add a benchmark-owned idempotent remittance receiver.
4. Replay the four HTTP/commit/queue failure variants.
5. Verify document, stock ledger, GL, outstanding balance, queue, and delivery
   invariants before admitting the task.

## Coding/DevOps candidate

Forgejo is the selected fully open candidate. The first source-backed task will
be chosen from package publication, releases and attachments, Actions runs, or
post-receive processing. Every coding workflow must include a durable effect
beyond repository files.
