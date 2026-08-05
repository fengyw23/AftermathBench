# Model Evidence Accounting

## Purpose

This document separates task construction from model evidence. A native task
does not cease to have been tested merely because the release package later
acquires stronger provenance requirements. Historical model experiments remain
development evidence. They are not silently relabelled as current leaderboard
results when their instance, visible tool contract, or evaluator semantics have
changed.

The repository therefore reports three counts instead of one:

| Label | Meaning | Use in claims |
|---|---|---|
| `hard-admitted` | Native prefix, failure boundary, reference recovery and fixed-policy admission pass. | Construction coverage. |
| `ordinary-model-tested` | A strong model received no recovery-scope answer and was deterministically scored. | Development difficulty evidence. |
| `current-formal-model-tested` | The ordinary run is bound to the current formal input lock and current public contract. | Release/leaderboard evidence. |

An explicit-scope execution control is deliberately not an ordinary model test:
it establishes that the agent can execute a supplied recovery direction.

## Existing Ordinary-Model Evidence

The following **25 matched failure states** have already received ordinary,
no-supplied-scope evaluation from a strong model and remain replay-admitted
hard development states. They must be retained in progress reports and should
not be rerun merely to increase a counter.

| Family / instance | States | Model evidence | Result | Source |
|---|---:|---|---:|---|
| Kubernetes constraint interactions, `dev-005` | 13 | GLM-5.2 | 2/13, matched group failed | `data/evidence/kubernetes-interaction-ordinary-glm52-20260804/` |
| ERPNext manufacturing rework, `dev-002` | 4 | GLM-5.2 | 3/4, matched group failed | `docs/CROSS_DOMAIN_VALIDATION_STATUS_20260804.md` |
| ERPNext shared-batch corrective recovery, `dev-001` | 4 | GLM-5.2 | 2/4, matched group failed | `data/evidence/erpnext-shared-batch-ordinary-glm52-20260804/` |
| Forgejo package provenance r2 | 4 | GLM-5.2; DeepSeek-V4-Pro | both 4/4, matched group passed | `docs/CROSS_DOMAIN_VALIDATION_STATUS_20260804.md` |

The package-provenance family is a useful positive control, not a hard
leaderboard family: strong models saturate it. The other three rows contain
real ordinary-recovery failures after the corresponding execution controls
passed, so their difficulty cannot be attributed to a missing tool surface.

## Historical Diagnostics

The following **12 states** have strong-model trajectories but cannot be
promoted to the current task definition without an equivalence audit. They
remain valuable construction evidence.

| Family / instance | States | Why not current-formal evidence | Source |
|---|---:|---|---|
| Forgejo release publication, `dev-002` | 8 | The old public contract did not state the replay-delivery identity rule; the later contract audit changed the visible semantics. | `docs/FORGEJO_PUBLICATION_MODEL_EXPERIMENT.md` |
| ERPNext sales return, old `dev-001` | 4 | The current formal instance is `erpnext-sales-return-public-dev-001-r1`, not the historical instance. | `data/evidence/erpnext-sales-return-ordinary-20260730/` |

The historical sales-return family additionally has DeepSeek-V4-Pro evidence;
the early easy-versus-holdout study is retained under
`data/evidence/erpnext-*-final-valid-20260729/` and is not counted as a
current native-hard result.

## What Requires a Rerun

A rerun is required only for one of these reasons:

1. the actual public scenario/instance changed;
2. the model-visible tool contract changed;
3. the deterministic evaluator changed;
4. raw trajectories are unavailable to establish the prior experiment's
   identity; or
5. the state is frozen hidden test data and has intentionally never been shown
   to a model.

It is **not** required simply because a new formal release manifest was added.

## Next Coverage Order

1. Preserve the 25 existing ordinary-model-tested states in every status
   report.
2. Add ordinary GLM-5.2 runs to public hard families without any existing
   ordinary trajectory, starting with the four current formal public slots.
3. Promote a historical result to `current-formal-model-tested` by an
   equivalence audit whenever the archived scenario, tool contract and
   evaluator fingerprints match the current lock. No provider call is needed
   for that promotion.
4. Freeze and evaluate hidden states only after the public interface and
   evaluator are stable. Hidden results are one-shot and must never guide task
   tuning.

## Reporting Language

Until every public run is lock-bound, use:

> AftermathBench currently contains 94 replay-admitted hard failure states. At
> least 25 have already undergone ordinary strong-model recovery evaluation;
> twelve additional historical states retain model trajectories but correspond
> to superseded public task definitions. Current-formal, cross-model coverage
> is the next release task.
