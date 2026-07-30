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

## Historical native challenge vertical slice

This section records the experiment under the gate used at the time. The
current stricter admission rule requires at least four recovery mutations;
the partial-return family has three and is now reported as `candidate`.
The result remains valid historical model evidence but is not counted as a
current hard-split release result.

The first native model pilot completed in GitHub Actions run
[`30382460087`](https://github.com/fengyw23/AftermathBench/actions/runs/30382460087)
at commit `a84337d1e0f52cf83d50144cf13d8f196dc2a93d`. `glm-5.2` passed all four
matched hidden states in one repetition. It selected submit, no write,
remittance requeue, and worker resume respectively, after inspecting the
authoritative payment and remittance state. There were no unsafe retries,
unnecessary requeues, tool errors, duplicate payments, or duplicate
remittance attempts.

This validates the native model interface but also shows that the first task
is too clean to separate a strong model: each hidden state has a direct
decision-complete signature. The sanitized complete trajectories are stored
under `data/evidence/erpnext-glm52-pilot-20260729`.

The follow-up hard family is now implemented as
`erpnext-partial-return-{dev,holdout}-001`. It starts after 17 successful native
writes and combines a partial Purchase Return, replacement procurement,
supplier credit, two invoices sharing one Payment Entry, stock and GL effects,
and an exactly-once supplier-pickup notification. The same visible connection
loss hides four transition states: no commit, committed response loss,
committed without pickup enqueue, and pickup job pending.

Complexity is computed from replayed native evidence rather than copied from
author labels. The family contains 18 relevant entities, 19 causal edges across
11 relation types, dependency depth 6, three independent evidence groups,
three required mutations, and two downstream repairs. The easy payment pilot
is rejected from the hard split by this same admission gate.

Deterministic validity controls pass:

- the reference recovery passes all four variants;
- seven fixed policies each score 0/4 and matched-group success is zero;
- the model execution control, which reveals the intended recovery scope but
  not the hidden transition state, scores 4/4 in Actions run
  [`30399812129`](https://github.com/fengyw23/AftermathBench/actions/runs/30399812129);
- the development GLM-5.2 run scores 1/4 in Actions run
  [`30395653247`](https://github.com/fengyw23/AftermathBench/actions/runs/30395653247).

In all three failed development trajectories the model completed the business
goal and preserved valid prefix effects, but created a duplicate replacement
invoice because it did not query invoices already linked to the replacement
receipt. This is classified as an investigation failure, not an interface or
provider failure. The frozen holdout was committed before any model call; the
repeated easy-versus-holdout comparison and its complete trajectories are
reported in `docs/GLM52_24H_REPORT.md`.

The final same-job comparison completed in Actions run
[`30407901921`](https://github.com/fengyw23/AftermathBench/actions/runs/30407901921)
at experiment commit `afcf9638b4cc4e3c4f031dda146a8edc6e246c16`:

- easy payment pilot: 20/20 Recovery Integrity, 5/5 matched groups;
- frozen hard holdout: 6/20 Recovery Integrity, 0/5 matched groups;
- absolute pass-rate reduction: 70 percentage points;
- hard Goal Completion, Repair Completeness, and Preservation: 100%;
- hard Protocol Safety: 30%;
- provider/runtime errors, retries, and model tool-call errors: zero.

All 14 hard failures completed the visible business goal but created a
duplicate replacement invoice without first listing invoices already linked
to the replacement receipt. The finding is therefore a reproducible
post-commit downstream-effect investigation failure rather than an interface
failure. Sanitized raw trajectories and the independent post-hoc analysis are
stored under `data/evidence/erpnext-glm52-final-valid-20260729`.

## Coding/DevOps candidate

Forgejo is the selected fully open candidate. The first source-backed task will
be chosen from package publication, releases and attachments, Actions runs, or
post-receive processing. Every coding workflow must include a durable effect
beyond repository files.

## Kubernetes constraint-interaction vertical slice

The fifth Kubernetes iteration moves beyond a four-leaf commit-state task. It
combines a monotonic schema catalog, two independently deployed consumers, a
shared credential, a temporary compatibility bridge, a non-replayable worker
batch, controller-owned Jobs, and exactly-once external registry events. The
same connection-loss result hides 13 native states requiring 13 distinct
recovery directions.

Native construction admission passed in GitHub Actions run
[`30483281549`](https://github.com/fengyw23/AftermathBench/actions/runs/30483281549)
at source commit `2be631e50b7c86183d2e4214ec77f266fef2b682`:

- reference recovery passed 13/13 states using only public model tools;
- 30/30 semantic relations replayed against native terminal evidence;
- ten evidence projections all had matched witnesses whose recovery direction
  changed after one fact group was restored;
- prompt audit found zero recovery-direction leaks across 14 complete input
  surfaces;
- nine fixed policies produced no matched-group solver. The strongest compact
  tree passed 6/13 (46.15%).

The task is admitted as hard for model validation, not yet as a finished
benchmark family. The exact-target execution control and ordinary GLM-5.2
experiment remain the next gates. Full replay evidence is archived under
`data/evidence/kubernetes-constraint-interaction-admission-final-20260730`.
