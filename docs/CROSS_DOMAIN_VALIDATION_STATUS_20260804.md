# Cross-domain validation status — 2026-08-04

This document separates scientific task evidence from packaging and model-result
evidence. A row is marked complete only when its underlying artifact is immutable,
hash-addressed, and replayable. Pending runs are not used to support benchmark
claims.

## Current evidence matrix

| Domain / family | Native failure boundaries | Exact replay + reference | Replay-derived hard admission | Fixed-policy matched-group resistance | Execution control | Ordinary model experiment | Formal release package |
|---|---:|---|---|---|---|---|---|
| Kubernetes constraint interactions | 13 | complete (13/13) | complete | complete (0 matched groups; best per-task policy 46.15%) | not yet run on current interface | not yet run on current interface | native evidence archived; release integration pending |
| Forgejo package provenance r2 | 4 | complete (4/4) | complete | complete (0/4 for every fixed policy) | complete (GLM-5.2 4/4; DeepSeek-V4-Pro 4/4) | complete but saturated (both models 4/4) | valid diagnostic frozen; formal release integration pending |
| ERPNext manufacturing rework | 4 | complete (4/4) | complete | complete (28 policy-boundary runs) | complete (GLM-5.2 4/4) | not yet validly run | rerun 30858814166 pending |

## What is already established

### Kubernetes

Run [30840277757](https://github.com/fengyw23/AftermathBench/actions/runs/30840277757)
provides 13 distinct native boundaries and 13 distinct semantic recovery scopes.
All references pass. The observed graph has 28 relevant entities, 30 semantic
edges, dependency depth 8, and six evidence groups. Across 117 fixed-policy
replays, no policy solves the full matched group; the strongest policy solves
46.15% of individual boundaries. This establishes directional hardness against
fixed recovery rules, but it is not yet a current-interface model result.

### Forgejo

Run [30853698178](https://github.com/fengyw23/AftermathBench/actions/runs/30853698178)
establishes four non-monotonic package-provenance boundaries. The observed graph
contains 35 entities, 47 edges, dependency depth 12, and seven evidence groups.
The minimum adaptive investigation depth is six queries, the minimum reference
repair uses six mutations, and no fixed policy passes any boundary.

The execution surface has independent 4/4 controls from GLM-5.2
([30857320582](https://github.com/fengyw23/AftermathBench/actions/runs/30857320582))
and DeepSeek-V4-Pro
([30857995305](https://github.com/fengyw23/AftermathBench/actions/runs/30857995305)).
These controls prove that a model can execute a supplied correct scope; they do
not measure whether it can infer that scope. Ordinary dual-model run
[30858985560](https://github.com/fengyw23/AftermathBench/actions/runs/30858985560)
then measured that question under the finalized evaluator. GLM-5.2 and
DeepSeek-V4-Pro both passed 4/4 with matched-group success, including the
valid-package-preserve versus corrupt-package-rebuild scope flip. This family
is therefore scientifically valid but saturated, and is retained as a control
rather than presented as evidence that current strong models struggle.

### ERPNext

Run [30854627801](https://github.com/fengyw23/AftermathBench/actions/runs/30854627801)
passed source construction, exact boundary/reference replay, all fixed-policy
replays, hard admission, formal-input locking, and a 4/4 GLM-5.2 execution
control. Its scientific task evidence is valid. It failed only while assembling
the seven-role authoritative release package, so it is not declared formal
release evidence. Rerun 30858814166 contains named contract diagnostics and the
input roles needed for offline repair if packaging fails again.

## Claim boundary

The repository currently supports the following narrow claim:

> AftermathBench has replay-valid difficult recovery families in three native
> systems, and two of those families have controls showing that their public
> tool surfaces are executable when the correct scope is supplied.

It does **not** yet support a top-conference benchmark claim. Missing evidence is:

1. a sealed ERPNext formal package and subsequent ordinary-model evaluation;
2. current-interface Kubernetes execution controls and model experiments;
3. unsaturated ordinary recovery families with interacting native obligations;
4. more independent families and hidden instances per domain;
5. a frozen cross-model leaderboard with repeated runs.

## Immediate decision rule

1. If Forgejo ordinary models fail after collecting the decisive evidence, expand
   that failure mode into independent hidden instances.
2. If they fail before collecting evidence, prioritize investigation-structure
   variants and measure evidence acquisition separately from repair execution.
3. If they pass all four boundaries, treat this development family as saturated;
   preserve it as an easy/control family and add interacting provenance, approval,
   and external-delivery dependencies rather than interface friction.
4. If ERPNext packaging succeeds, import and seal it immediately. If it fails,
   repair the named formal contract offline from the archived input roles before
   any new native rerun.
