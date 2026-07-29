# Kubernetes settlement iteration 001

## Result

The first executable settlement scenario is valid, but it is not a hard
recovery task.

| Check | Result |
|---|---:|
| Native boundary replay | 4/4 |
| Public-tool reference recovery | 4/4 |
| GLM-5.2 without execution control | 4/4 |
| `compact_state_tree` | 4/4 |
| `assume_committed` | 3/4 |
| `blind_retry` | 1/4 |

The authoritative evidence is archived in
`data/evidence/kubernetes-settlement-candidate-glm52-bailian-20260729`.
The code and evidence are frozen by Git tag
`k8s-settlement-candidate-v0.1`.

## What the experiment actually measured

The model had to determine whether a generated-name Job was absent, completed,
suspended, or blocked by a Node taint. It then preserved the prior settlement
and completed the target Lease, external delivery, receipt, and ledger. This is
a real cross-system recovery: all effects are native Kubernetes objects or a
durable idempotent receiver record, and all model actions map to ordinary public
operations.

However, only the primary Job branch varied. Once the Job became complete, the
remaining state was identical in all four variants. Consequently the task
collapsed to a small decision tree followed by one fixed downstream suffix.
Counting objects, relations, queries, or mutations did not expose that
structural simplicity.

## Evaluator defect discovered by the model run

The first evaluator required receipt status `complete`, while the Job log shown
to the model emitted `approved`. GLM-5.2 copied the authoritative visible value
and was initially marked wrong in all four trajectories. The evaluator was
corrected, the old raw outputs were retained, and a fresh run passed 4/4.

This yields a construction rule: every scored literal must be traceable to the
user instruction, an ordinary tool result, or a documented controller rule.
Benchmark difficulty may not come from private status vocabulary.

## Required change for iteration 002

The next scenario must vary independently completed downstream effects behind
the same surface error. The primary Job state alone must not determine the
repair scope. In particular, matched variants will contain different
combinations of:

- Job absent, suspended, or complete;
- idempotency Lease absent or present;
- receipt absent or present in a visible pending/approved state;
- external delivery absent or already durably accepted;
- audit record absent or present;
- monthly schedule marker absent or present.

Every state is produced by real writes before the visible error, not by hidden
manifest labels. The correct recovery must preserve already completed effects,
repair only missing or inconsistent branches, and verify the whole closure.

## Revised hard-task criterion

A task is not hard merely because its reference trace contains many operations.
It becomes a hard candidate only when all of the following hold:

1. at least two downstream action branches vary across matched states;
2. at least three distinct correct mutation signatures are observed;
3. no primary-record-only decision tree solves the matched group;
4. no fixed downstream suffix solves the matched group;
5. every relation and scored value has replayable public evidence;
6. the reference and execution-control conditions remain reliable;
7. model failures arise from investigation, inference, scope, execution, or
   verification, rather than tool ambiguity.

This criterion is domain-independent and can later be applied to ERP, Git,
Kubernetes, ITSM, cloud operations, and coding recovery tasks.
