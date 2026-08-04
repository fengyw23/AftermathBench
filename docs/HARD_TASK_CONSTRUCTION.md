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

## Recovery-time state invalidation

Boundary reconstruction alone is not sufficient for the hardest tasks. A
repair mutation can activate native hooks, controllers, or queued work and
thereby invalidate facts collected before that mutation. Any later decision
that depends on those facts must use the mutation result or refresh the
authoritative state.

The sales-return development run exposed both forms of the same safety
failure:

- a downstream invoice already existed at the ambiguous failure boundary, but
  the agent did not enumerate linked invoices before creating another;
- no invoice existed at the boundary, but submitting the replacement Delivery
  Note caused native automation to create one, and the agent continued an
  already planned create call without refreshing state.

The second case is not a sequence-format puzzle. The write has an authentic
persistent downstream effect, the effect is observable through ordinary
relation queries, and multiple tool orders are legal. The terminal evaluator
still accepts any safe trajectory; trajectory analysis separately records
whether a stale post-mutation belief caused the failure.

Future hard families should therefore include replay-witnessed
**state-invalidation edges** when the native system supports them:

- a public write can create or advance a downstream object without returning
  the complete new dependency closure;
- a subsequent mutation is safe only after inspecting the relevant result or
  authoritative relation;
- the necessary observation is available through an ordinary public tool;
- the reference and explicit-scope control demonstrate a valid recovery
  within the same turn budget; and
- the evaluator rejects duplicate or conflicting effects, not the omission of
  a particular query sequence.

This dimension tests adaptive recovery rather than a one-shot plan computed
from the initial failure snapshot.

## Scope-decision depth, not reference-trace length

Forgejo package-provenance r2 passed replay-derived hard admission but both
GLM-5.2 and DeepSeek-V4-Pro solved all four ordinary boundaries. The result
exposed a limitation in the earlier admission metric. Adaptive query depth
measured how many reference queries used identifiers discovered by previous
queries; it did not measure how many independent observations were actually
needed to select the gold recovery scope. A long provenance walk can coexist
with a single inventory response that reveals the correct scope.

New families may therefore provide a complete `scope_decision_matrix`. Each
row binds a matched variant to its gold recovery signature and the canonical
result of every declared public observation surface. The audit computes:

- whether different gold scopes are observable at all;
- whether one query surface alone solves the complete matched group;
- the smallest static set of surfaces that separates every pair of different
  scopes; and
- the optimal adaptive decision tree's worst-case query depth.

The implementation is
`aftermath_bench.scope_decision_audit.analyze_scope_decision_matrix`. When a
scenario declares an admission profile under `scope_decision`, the matrix is
hash-bound as an admission input. The default hard gate requires both a static
certificate size and an adaptive worst-case depth of at least two, and rejects
any single-surface solver. This does not require the Agent to follow a fixed
query order. It rejects only tasks whose recovery-scope decision is
information-theoretically simpler than their surrounding graph suggests.

## Intervention-plan complexity, not evidence depth alone

The source-bound Forgejo cross-system reconciliation family exposed a second
limitation. Its six matched boundaries require all six evidence surfaces in
both the smallest static certificate and the optimal adaptive decision tree;
the strongest fixed policy passes only two boundaries. Nevertheless, GLM-5.2
passes both the explicit-scope control and ordinary condition 6/6. Every
boundary contains at most one missing obligation, and every missing obligation
maps to one local repair operator. Once the model queries all evidence, repair
is a direct lookup.

Hard admission must therefore measure two independent structures:

- **evidence complexity:** which observations are needed to reconstruct the
  boundary state;
- **intervention complexity:** how mutation operators compose, overlap and
  threaten already-valid effects.

The design-time implementation is
`aftermath_bench.intervention_plan_audit.audit_intervention_design`. It models
public mutations by their preconditions, repaired obligations, invalidated
obligations and duplicate/destructive application conditions. It computes safe
minimal plans for every boundary and rejects a one-gap/one-local-repair star.
The next native hard family must include multiple boundaries requiring composed
repairs, overlapping mutation effects, context-sensitive operators and
plausible unsafe shortcuts. These declarations are only a design gate: native
replay must later verify every operator effect before admission.

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
- no single public observation surface can select the correct scope for the
  complete matched group, and the scope-decision matrix is itself replayed and
  hash-bound;
- the reference and explicit-scope controls succeed;
- the evaluator depends only on native terminal state and auditable external
  delivery records; and
- the evaluator compares durable effects with the failure boundary, rejects
  creation of unrequired obligations even when the terminal state is
  internally consistent, and has a regression test that injects such an
  over-repair;
- sentinel values such as `none`, `unknown`, and `not-applicable` have a
  model-visible rule stating the exact object-existence condition that selects
  them; failed, cancelled, or pending objects are not silently treated as
  absent;
- failures can be attributed to investigation, state inference, scope,
  execution, or verification.

For matched counterfactual groups, provenance counts alone are insufficient.
Each declared decision-relevant evidence group must have a **projection
witness**: two replayed boundaries require different recovery scopes, but
become indistinguishable after only that group's fact keys are removed. This
rejects impressive-looking yet redundant evidence sources. The reusable
implementation is `aftermath_bench.evidence_projection`; the Kubernetes
iteration-004 audit demonstrates witnesses for commit state, escaped
preparation and release publication.

See `BOUNDARY_RELATIVE_RECOVERY_INTEGRITY.md` for the formal effect-envelope
rule and cross-domain examples.

This pattern can later be transferred to ITSM, cloud operations, and coding
tasks, but each domain needs native states and invariants rather than renamed
ERP records.

## Cross-obligation replay gate

Graph size and long query traces do not prove that a recovery decision is hard.
New unsaturated families can therefore opt into `obligation_interaction`
admission. The associated artifact restores each exact boundary, applies a
public-tool semantic action, and records the deterministic evaluator vector
before and after the action. Admission derives two kinds of witnesses:

- a cross-obligation witness changes at least two terminal obligations; and
- a repair-preservation conflict makes an unsatisfied obligation true while
  making a protected, previously true obligation false.

Every probe must contain public tool events and a native result-state SHA-256.
The reusable implementation is
`aftermath_bench.obligation_interaction_audit`; author-written labels do not
count. The first intended application is the native ERPNext shared-batch
manufacturing family specified in `CROSS_OBLIGATION_FAMILY_SPEC.md`.

## Frozen holdout outcome

The final same-job comparison in Actions run
[`30407901921`](https://github.com/fengyw23/AftermathBench/actions/runs/30407901921)
passed every pre-registered acceptance check:

- easy pilot Recovery Integrity: 20/20;
- frozen holdout Recovery Integrity: 6/20;
- absolute reduction: 70 percentage points;
- frozen holdout matched-group success: 0/5;
- reference recovery: 4/4;
- explicit-scope execution control: 4/4;
- provider/runtime and model tool-call errors: zero.

The hard model completed Goal Completion, Repair Completeness, and Preservation
in all 20 runs, but Protocol Safety in only 6. The 14 failures all skipped the
query that would enumerate an already-created downstream replacement invoice
and then created a duplicate. The one successful committed-state repetition
performed that list query and reused the existing invoice. This supports the
construction principle that difficulty should come from reconstructing
transitive post-commit effects, not from hiding evidence or making tools
ambiguous.
