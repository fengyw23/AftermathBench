# Kubernetes settlement iteration 002

## Outcome

Iteration 002 successfully increased structural recovery complexity, but did
not yet create a challenging strong-model task.

| Signal | Result |
|---|---:|
| Native boundaries | 4/4 |
| Reference recoveries | 4/4 |
| Distinct partial states | 4 |
| Distinct reference mutation signatures | 4 |
| Minimum reference mutations | 5 |
| Maximum fixed-policy pass rate | 25% |
| Replay-derived hard admission | pass |
| GLM-5.2 valid score | 4/4 |

The raw model summary said 0/4. That number is invalid: all four trajectories
failed only because the evaluator required a duplicate receipt hash inside the
audit ConfigMap, although neither the user request nor policy required it. The
model correctly wrote batch, recorded status and actual Job UID. Removing this
unobservable convention changes all four outcomes to pass without changing any
model action.

## What improved

Unlike iteration 001, the matched states independently vary the Job, Lease,
pending receipt, settlement delivery and audit delivery. A fixed full suffix
duplicates an existing exactly-once effect in three states and passes only one.
The task therefore measures real investigation and idempotent execution rather
than only the primary Job state.

The hard admission is also now replay-derived. It verifies 23 entities, 23
relations, dependency depth 10, four evidence groups, four recovery signatures,
three varying action branches and executed fixed policies.

## Why GLM still solved it

Despite the larger state graph, every variant has the same recovery direction:

> preserve all valid effects and forward-complete every missing obligation.

The model can enumerate the user-stated checklist, query each record, and fill
the missing entries independently. The task has branching over *whether an
action is needed*, but not over *which recovery direction is correct*. More
objects and more independent idempotency checks increase bookkeeping, not the
central recovery decision.

## Iteration 003 requirement

The next family must make the observed state change the semantic recovery
direction. Behind one failed operation, matched variants should require at
least three of the following:

- forward-complete an irreversible migration;
- roll back an uncommitted candidate while preserving the stable service;
- compensate an already externalized effect;
- repair only a downstream controller record;
- leave a completed path unchanged.

A promising Kubernetes family is a schema migration plus application rollout:
backup, migration Job, database schema epoch, candidate Deployment, Service
traffic, Secret rotation, rollback compatibility, external release registry and
audit event. If the schema migration never committed, rollback can be correct;
if it committed past a backward-compatibility boundary, rollback becomes unsafe
and forward completion is required. Other variants can have traffic or registry
effects already applied. All facts must be visible through ordinary Kubernetes,
database-status and registry tools.

This is the design change that matters. Adding a third receipt, queue or
ConfigMap to the current forward-only checklist would not address the observed
model saturation.
