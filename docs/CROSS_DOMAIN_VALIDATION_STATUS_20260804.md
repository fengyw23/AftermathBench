# Cross-domain validation status — 2026-08-04

This document separates scientific task evidence from packaging and model-result
evidence. A row is marked complete only when its underlying artifact is immutable,
hash-addressed, and replayable. Pending runs are not used to support benchmark
claims.

## Current evidence matrix

| Domain / family | Native failure boundaries | Exact replay + reference | Replay-derived hard admission | Fixed-policy matched-group resistance | Execution control | Ordinary model experiment | Formal release package |
|---|---:|---|---|---|---|---|---|
| Kubernetes constraint interactions | 13 | complete (13/13) | complete | complete (0 matched groups; best per-task policy 46.15%) | complete (GLM-5.2 12/13; 92.31%) | complete (GLM-5.2 2/13; 15.38%; 0 provider errors) | complete raw coverage archive; release integration pending |
| Forgejo package provenance r2 | 4 | complete (4/4) | complete | complete (0/4 for every fixed policy) | complete (GLM-5.2 4/4; DeepSeek-V4-Pro 4/4) | complete but saturated (both models 4/4) | valid diagnostic frozen; formal release integration pending |
| ERPNext manufacturing rework | 4 | complete (4/4) | complete | complete (28 policy-boundary runs) | complete (GLM-5.2 4/4) | complete (GLM-5.2 3/4; matched group failed) | complete; formally bound as `dev-002` |
| ERPNext shared-batch corrective recovery | 4 | complete (4/4) | complete | complete (best fixed policy 1/4; no matched-group solver) | complete (GLM-5.2 4/4) | complete (GLM-5.2 2/4; matched group failed) | hard-admitted development evidence; formal integration pending |

## What is already established

### Kubernetes

Run [30840277757](https://github.com/fengyw23/AftermathBench/actions/runs/30840277757)
provides 13 distinct native boundaries and 13 distinct semantic recovery scopes.
All references pass. The observed graph has 28 relevant entities, 30 semantic
edges, dependency depth 8, and six evidence groups. Across 117 fixed-policy
replays, no policy solves the full matched group; the strongest policy solves
46.15% of individual boundaries. This establishes directional hardness against
fixed recovery rules, but it is not yet a current-interface model result.

A retrospective scope-decision audit now binds all 13 exact boundaries to five
ordinary query surfaces: catalog/batch records, consumer Deployments, the shared
credential Secret, controller Jobs, and the external registry. All five surfaces
are required by the smallest static certificate, while the optimal adaptive
decision tree has worst-case depth three. No single surface solves the matched
group. This is materially stronger than reference-trace length: it proves the
different recovery scopes require composed boundary observations. Because this
gate was added after family construction, it is reported as a retrospective
audit; future families must freeze the matrix and thresholds before model runs.

Current-interface execution control
[30860821930](https://github.com/fengyw23/AftermathBench/actions/runs/30860821930)
passed 12/13 states (92.31%), above the predeclared 80% gate, with zero
infrastructure errors and complete six-group investigation before every first
write. In the sole failure (`state_03`), GLM-5.2 created the required suspended
transition-owner Job but incorrectly also labeled it as a migration Job. The
strict evaluator consequently detected duplicate migration ownership and stale
UIDs in the audit/closure records. This is a model execution error after correct
scope identification, not missing evidence or interface ambiguity. Ordinary
scope-inference run
[30865035666](https://github.com/fengyw23/AftermathBench/actions/runs/30865035666)
completed scored trajectories for 11 states; a non-replacing provider retry
[30872359883](https://github.com/fengyw23/AftermathBench/actions/runs/30872359883)
filled only the two missing states. The deterministic union therefore contains
all 13 states without replacing any scored primary trajectory. GLM-5.2 passed
2/13 (15.38%); matched-group success was false, Goal Completion was 8/13
(61.54%), Preservation was 12/13 (92.31%), Protocol Safety was 8/13 (61.54%),
and Repair Completeness was 2/13 (15.38%). All eleven failures are classified as
scope failures. The complete raw union, source run IDs, source and target hashes,
summary, and analysis are frozen under
`data/evidence/kubernetes-interaction-ordinary-glm52-20260804/`. This closes the
provider-coverage gap and supports recovery-scope composition difficulty rather
than missing tools or provider instability.

An earlier dispatch
[30864390353](https://github.com/fengyw23/AftermathBench/actions/runs/30864390353)
stopped during preflight because a source hash generated from Windows line
endings did not match the Linux LF checkout; it reached neither the native
runtime nor the model and is excluded from experiment counts. The source-lock
test now normalizes to the repository's declared LF release bytes.

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

Run [30858814166](https://github.com/fengyw23/AftermathBench/actions/runs/30858814166)
passed source construction, boundary/reference replay, all fixed-policy replays,
hard admission, formal-input locking, and a 4/4 GLM-5.2 execution control. Its
only workflow failure was the generic release validator requiring byte-identical
reference starts even though this family already had a trusted semantic
projection for terminal RQ audit rows. The archived inputs were completed
offline after fixing that inconsistency. The seven-role package now validates
and is formally bound as `erpnext/erpnext-manufacturing-rework/dev-002`; no
native runtime or provider rerun was needed.

The ordinary no-supplied-scope GLM-5.2 experiment
[30864156919](https://github.com/fengyw23/AftermathBench/actions/runs/30864156919)
against the formally bound public `dev-002` instance passed 3/4 boundaries, so
matched-group success was false. All four runs completed the manufacturing goal,
preserved protected documents, and queried documents, asynchronous state, and
ledgers. The `request_not_reached` run failed only protocol safety: submitting
the draft corrective Job Card automatically activated its known `on_submit`
Webhook, after which the model explicitly enqueued the same Webhook again. The
receiver returned two attempts, but the model still declared the release
exactly-once. The Webhook name was supplied in the initial context and was
queryable through generic `get_document`; therefore this is a cross-system
side-effect reasoning and verification error, not a hidden constraint.

The independent shared-batch development family passed its strict native gate in
[30879081393](https://github.com/fengyw23/AftermathBench/actions/runs/30879081393).
Its replay-derived admission records 42 successful prefix writes, 27 relevant
entities, 25 replayed semantic relations, dependency depth 7, five evidence
groups, four distinct recovery signatures, and no single-surface scope solver.
All four references pass. Twelve replay-bound destructive probes cover three
different native cancellation actions and produce twelve repair/preservation
conflicts across all four boundaries. Seven fixed strategies were run against
every boundary; the strongest solves only 1/4 and none solves the matched group.
The exact same public tool surface already passed a 4/4 GLM-5.2 execution control
in [30873838931](https://github.com/fengyw23/AftermathBench/actions/runs/30873838931).
The ordinary no-supplied-scope condition
[30881911583](https://github.com/fengyw23/AftermathBench/actions/runs/30881911583)
completed all four boundaries without provider errors. GLM-5.2 passed 2/4 and
failed the matched group. Goal completion and preservation were 4/4; repair
completeness and protocol safety were 2/4. In both failures, the model repaired
the manufacturing state but enqueued a second certificate delivery while an
existing asynchronous owner was pending. The receiver retained one logical
certificate but audited two attempts, and the model then incorrectly described
those two attempts as "exactly once". Full trajectories and a hash manifest are
frozen under
`data/evidence/erpnext-shared-batch-ordinary-glm52-20260804/`.

## Claim boundary

The repository currently supports the following narrow claim:

> AftermathBench has replay-valid difficult recovery families in three native
> systems, and all three systems have controls showing that their public
> tool surfaces are executable when the correct scope is supplied.

It does **not** yet support a top-conference benchmark claim. Missing evidence is:

1. unsaturated ordinary recovery families with interacting native obligations;
2. more independent families and hidden instances per domain;
3. a frozen cross-model leaderboard with repeated runs.

## Active directional risks and closure gates

The next development cycle is intentionally constrained by three risks. They
are not considered closed by adding more variants to an existing template.

1. **ERP state-dimensionality risk.** The current shared-batch family varies a
   Job Card and its certificate delivery. A second native ERP family must place
   the ambiguous failure at an inventory/accounting boundary and produce
   objectively different Stock Ledger, GL, shared-cost, and asynchronous repost
   states. Merely adding more protected documents does not close this risk.
2. **Instance-independence risk.** A family needs at least two independently
   parameterized business instances whose item identities are disjoint and whose
   quantities or dependency topology differ. Both must pass the same replay,
   reference, fixed-policy, and admission pipeline. The second shared-batch
   instance is currently under native replay and is not counted until that run
   passes.
3. **Forgejo saturation risk.** Package provenance remains an executable control,
   but its 4/4 ordinary-model result cannot support a hardness claim. The next
   Forgejo difficulty family must cross approval state, signed build artifacts,
   deployment status, external publication/attestation, and preservation of a
   prior release; it must pass execution control while failing matched-group
   inference for at least one strong model.

These gates keep effort focused on new recovery reasoning rather than increasing
case count through surface-level renaming.

## Immediate decision rule

1. If Forgejo ordinary models fail after collecting the decisive evidence, expand
   that failure mode into independent hidden instances.
2. If they fail before collecting evidence, prioritize investigation-structure
   variants and measure evidence acquisition separately from repair execution.
3. If they pass all four boundaries, treat this development family as saturated;
   preserve it as an easy/control family and add interacting provenance, approval,
   and external-delivery dependencies rather than interface friction.
4. ERPNext packaging is now sealed. Use the next provider budget on ordinary
   scope inference, not on repeating the already valid native control.
