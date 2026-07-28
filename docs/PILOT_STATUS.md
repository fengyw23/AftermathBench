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

The repository now contains:

- a digest-pinned MariaDB, Redis, Toxiproxy, gateway, remittance, and
  source-built ERPNext Compose topology;
- a seven-write public-API prefix builder;
- SQL dump/restore plus Redis and audit reset;
- executable controllers for request suppression, post-commit response loss,
  queue enqueue failure, and pending workers;
- deterministic checks over protected documents, stock ledger, invoice
  outstanding, Payment Entry references, balanced GL, RQ jobs, and remittance;
- a manual CI workflow that builds and replays all four variants.

Native execution admission passed on 2026-07-28 in GitHub Actions run
[`30373948156`](https://github.com/fengyw23/AftermathBench/actions/runs/30373948156)
at commit `61d3726b7ec45897cf5a31c10a151b2d61aab54b`. The workflow built the pinned
Frappe and ERPNext revisions from source, replayed the seven-write prefix,
restored the same SQL snapshot for each variant, and passed every native
failure-boundary assertion. The sanitized evidence artifact contained all four
reports and no API credentials.

The four observed states were:

- request not reached: no submitted payment and `$4,800` still outstanding;
- committed response lost: one submitted payment, no outstanding balance, and
  remittance delivered;
- after-commit enqueue failed: payment committed, but no job or remittance;
- async job pending: payment committed, one unfinished job, no remittance.

## Native recovery-control validation

GitHub Actions run
[`30379601930`](https://github.com/fengyw23/AftermathBench/actions/runs/30379601930)
validated one state-driven reference control against all four hidden states at
commit `f5c5dc0e2a21566efe5607c08f4baddcc9d8cbda`. The control used only the same
restricted order, receipt, invoice, payment, GL, RQ-job, remittance, submit,
requeue, and worker tools intended for models. It did not read the variant
label.

The selected mutations were:

- request not reached: submit the still-draft Payment Entry;
- committed response lost: no write;
- after-commit enqueue failed: requeue the native remittance webhook;
- async job pending: resume the existing workers without requeueing.

All four final states passed. Each produced exactly one remittance delivery
attempt and zero unfinished relevant jobs.

## Next enterprise implementation

1. Connect the restricted ERPNext environment to the provider-agnostic model
   loop.
2. Reduce tracing overhead by replacing per-tool full evidence scans with
   incremental event fingerprints.
3. Evaluate language models on matched hidden states.

## Coding/DevOps candidate

Forgejo is the selected fully open candidate. The first source-backed task will
be chosen from package publication, releases and attachments, Actions runs, or
post-receive processing. Every coding workflow must include a durable effect
beyond repository files.
