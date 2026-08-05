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

## Registry-Certified Ordinary Evidence

`data/model_evidence_registry.json` is the machine-verifiable source of
ordinary-model counts. It currently certifies **29 unique states**: **25**
belong to the active 94 hard-admitted states and **4** are archived
shared-batch hard development states. The package-provenance r1 conditions
from GitHub run `30985786988` contribute four new active states; GLM-5.2 and
DeepSeek-V4-Pro observations of the same states are deliberately deduplicated.

The registry also records **12 historical-development states**, **29
control-only states**, and **zero current-formal ordinary states**. The
successful migration workflow run `30985603153` remains a quarantine receipt:
its artifact contains four prohibited restore archives, so its score is not
imported. A green workflow conclusion is never treated as a benchmark pass.

Every condition records the scenario and variant set, immutable source run or
archive, model/provider/repetition, summary and trajectory-set SHA-256 values,
the four deterministic components, error attribution, and an identity hash
over the scenario/tool/evaluator/formal-input-lock fingerprints. The validator
rejects duplicate run/condition records, execution-control masquerading as
ordinary evidence, and any current-formal promotion without an exact identity
match.

## Existing Ordinary-Model Evidence

The following **29 matched failure states** have received ordinary,
no-supplied-scope evaluation from a strong model and remain replay-admitted
hard development states. They must be retained in progress reports and should
not be rerun merely to increase a counter.

| Family / instance | States | Model evidence | Result | Source |
|---|---:|---|---:|---|
| Kubernetes constraint interactions, `dev-005` | 13 | GLM-5.2 | 2/13, matched group failed | `data/evidence/kubernetes-interaction-ordinary-glm52-20260804/` |
| ERPNext manufacturing rework, `dev-002` | 4 | GLM-5.2 | 3/4, matched group failed | `docs/CROSS_DOMAIN_VALIDATION_STATUS_20260804.md` |
| ERPNext shared-batch corrective recovery, `dev-001` | 4 | GLM-5.2 | 2/4, matched group failed | `data/evidence/erpnext-shared-batch-ordinary-glm52-20260804/` |
| Forgejo package provenance r2 | 4 | GLM-5.2; DeepSeek-V4-Pro | both 4/4, matched group passed | `docs/CROSS_DOMAIN_VALIDATION_STATUS_20260804.md` |
| Forgejo package provenance r1 | 4 | GLM-5.2; DeepSeek-V4-Pro | both 2/4, matched group failed | `data/evidence/model-runs/github-run-30985786988-package-r1-ordinary/` |

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

1. Preserve the 29 registry-certified ordinary-model-tested states in every
   status report, while keeping the 25 active and 4 archived subsets separate.
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

> AftermathBench currently contains 94 replay-admitted hard failure states. A
> machine-verified registry contains 29 unique ordinary strong-model states,
> of which 25 belong to the active set and 4 are archived hard development
> evidence. Twelve additional historical states retain trajectories from
> superseded task definitions. No current-formal ordinary state is certified
> yet; the 29 formal control states are control-only.
