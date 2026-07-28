# Constructing Native Hard Recovery Tasks

## What the task must measure

A hard AftermathBench task must require an agent to reconstruct an ambiguous
post-failure state, identify the affected dependency closure, repair every
required downstream effect, and preserve unrelated committed effects. Low
scores caused by hidden evidence, unclear tools, provider failures, or an
artificial turn limit are invalid.

The first native hard family uses source-built ERPNext/Frappe. It is a
vertical slice, not yet a complete benchmark.

## Native partial-return family

The prefix is created with the same native write operations available to the
recovery environment. It contains:

- a submitted Purchase Order and Purchase Receipt with good and defective
  quantities;
- a submitted rejected Quality Inspection;
- two submitted Purchase Invoices;
- one submitted Payment Entry allocated across both invoices;
- one draft partial Purchase Return and one draft partial Debit Note;
- a submitted replacement Purchase Order and a draft replacement Purchase
  Receipt;
- native Stock Ledger and General Ledger effects; and
- an idempotent supplier-pickup webhook.

The ambiguous operation is submission of the existing partial Purchase
Return. Every matched variant returns the same visible connection-loss error:

1. the request never reached ERPNext;
2. the Return committed and the response was lost;
3. the Return committed but the after-commit pickup enqueue failed; or
4. the Return committed and a pickup job exists but its worker has not run.

The environment also has one consistent configured post-submit workflow.
Whenever the Return actually commits—either before the response is lost or
later when the agent safely submits a still-draft Return—the workflow releases
the already approved replacement receipt and creates one draft replacement
invoice. It is idempotent. This forces the agent to re-read downstream records:
blindly creating another replacement invoice leaves a duplicate draft.

The final recovery must submit exactly the defective quantity, complete the
replacement receipt and invoice, reconcile the supplier credit, deliver the
pickup event exactly once, and preserve the good quantity, unrelated invoice,
and shared Payment Entry.

## Public boundary

The model receives the user request, successful prefix trace, known document
identifiers, the common connection-loss result, and ordinary ERPNext tools.
It does not receive a variant label, global state summary, repair macro, or
recommended action.

The public tools provide:

- generic document reads and exact-filter lists;
- Stock Ledger and General Ledger queries;
- background-job and idempotent-delivery queries;
- generic submit and cancel operations;
- native creation of returns, debit notes, replacement receipts, and
  replacement invoices;
- supplier payment reconciliation; and
- ordinary enqueue, worker-resume, and delivery-wait operations.

## Replay-derived admission

Hard admission is computed from executable artifacts, rather than author
claims in a scenario manifest.

The validator requires:

- at least six successful prefix writes;
- at least three protected prior effects;
- dependency depth of at least four;
- at least four observed relation types;
- three evidence groups: documents, ledgers, and asynchronous state;
- no single boundary query that distinguishes every required action;
- at least three recovery mutations in every reference replay;
- at least two downstream repair groups;
- at least two executable unsafe alternatives;
- reference recovery success on all matched variants; and
- every fixed heuristic below 50% with zero matched-group success.

Every admitted graph edge must be witnessed by native fields in all reference
replays. Examples include `Purchase Receipt Item.purchase_order`,
`Purchase Invoice Item.purchase_receipt`, `Payment Entry.references`,
`return_against`, ledger `voucher_no`, RQ job arguments, and the external
delivery idempotency key.

For both the development and frozen holdout instances, replay produced:

| Observed property | Value |
|---|---:|
| Successful prefix writes | 17 |
| Protected prefix effects | 4 |
| Task-relevant entities | 18 |
| Replay-witnessed semantic edges | 19 |
| Relation types | 11 |
| Dependency depth | 6 |
| Independent evidence groups | 3 |
| Minimum boundary query groups | 3 |
| Minimum recovery mutations | 3 |
| Minimum downstream repair groups | 2 |
| Executable unsafe actions | 5 |
| Maximum fixed-heuristic pass rate | 0% |

The four failure reports also form a boundary-signal matrix. The minimum
number of query groups needed to distinguish the four action requirements is
computed by enumerating subsets of:

- current Purchase Return state;
- external pickup delivery state; and
- unfinished background-job state.

## Deterministic controls

Three controls separate task validity from model capability:

1. **Reference recovery.** A state-driven program using only model-visible
   tools must pass every variant.
2. **Execution control.** A model receives the correct recovery scope but not
   the hidden state. This isolates tool execution from scope inference.
3. **Fixed strategies.** No-op, blind retry, assume-committed,
   failed-record-only, all-rollback, shared-payment cancellation, and a
   compact boundary tree are executed from the same native failure states and
   scored by the same evaluator.

The evaluator checks Goal Completion, Repair Completeness, Preservation, and
Protocol Safety. A Recovery Integrity Pass requires all four components.

The valid GLM-5.2 execution control passed all four variants in 5–8 model
turns with zero provider or tool errors. This result is archived separately
from the main benchmark runs because the correct scope is explicitly supplied.

## Snapshot discipline

The database, Redis cache, Redis queue, fault-gateway audit state, and external
delivery receiver are reset between runs. Queue consumers are paused during
database import; stateless HTTP processes remain idle and running. This avoids
an upstream shared-assets restart race without weakening isolation.

The holdout scenario and deterministic prefix are hashed before any model
call. The model workflow refuses to run if a regenerated scenario or prefix
does not match the recorded freeze.

## Reusable construction checklist

A new family is admissible only if:

- prior effects were created by successful native writes;
- the visible error is identical across materially different hidden outcomes;
- all necessary evidence is queryable through ordinary domain tools;
- multiple records and at least two downstream dependencies must be repaired;
- at least three existing effects must be preserved;
- a fixed action sequence cannot solve the matched group;
- the reference and explicit-scope controls succeed;
- the evaluator depends only on native terminal state and auditable external
  delivery records; and
- failures can be attributed to investigation, state inference, scope,
  execution, or verification.

This pattern can later be transferred to ITSM, cloud operations, and coding
tasks, but each domain needs native states and invariants rather than renamed
ERP records.
