# Forgejo package-publication model experiment

## Status

This is a complete paired development experiment for
`forgejo-release-publication-dev-002`. It is not a leaderboard result: the
family has one public development instance, one trial per matched boundary,
and no independently frozen hidden instance.

**Post-experiment contract audit.** The 7/8 ordinary result is retained as a
pre-contract diagnostic, not as clean evidence of a recovery-reasoning
failure. At the time of the run, the public tool contract did not state that
native replay copies the stored historical payload, creates a new delivery
UUID, and that the receiver keys idempotency by UUID rather than payload
hash. The trajectory contains a genuine identity-inference error, but it is
confounded by this missing operation semantics. The current interface now
publishes those stable rules and waits for an actually new history UUID.

## What is being tested

An approved release publication returns the same connection error in every
case. The agent must reconstruct what actually persisted across the Release,
three attachments, two native webhook histories, two external receiver
records and a milestone. It must complete only missing work, preserve
unrelated repository state and avoid duplicate externally visible effects.

The eight matched boundaries use the same user request and visible error but
require five distinct recovery signatures. The model never receives the
boundary label, evaluator, reference trace or a global repair summary.

## Native validity controls

GitHub Actions run
[`30558008600`](https://github.com/fengyw23/AftermathBench/actions/runs/30558008600)
rebuilt pinned Forgejo from source and replayed the full task family:

- 21 successful native writes precede the ambiguous failure;
- the public-tool reference passes 8/8 boundaries;
- all 30 semantic relations replay against native evidence, across 19
  relation types and dependency depth 6;
- the strict admission gate assigns `hard`;
- six fixed policies have zero matched-group success;
- the strongest fixed policy, `compact_release_tree`, passes 2/8.

Complete source, boundary, reference, baseline and admission artifacts are in
`data/evidence/forgejo-publication-native-final-20260731/`.

## Paired model design

Both model conditions use:

- source commit `0d4840df92a887c125f0a4288e90b564b9aabc85`;
- `glm-5.2` through the same Bailian OpenAI-compatible endpoint;
- the same scenario, public tools and 25-turn limit;
- a fresh restore and native boundary injection before each run;
- one trial for each of the eight matched boundaries;
- deterministic terminal-state scoring with no LLM judge.

The only intentional condition difference is that the execution control
receives the correct state-dependent recovery rule. The ordinary condition
must infer that rule from live evidence.

| Condition | Recovery Integrity | Matched group | Goal | Preservation | Protocol safety | Infrastructure errors |
|---|---:|---:|---:|---:|---:|---:|
| Reference program | 8/8 | 1/1 | 8/8 | 8/8 | 8/8 | 0 |
| Best fixed policy | 2/8 | 0/1 | — | — | — | 0 |
| Explicit-scope control | 8/8 | 1/1 | 8/8 | 8/8 | 8/8 | 0 |
| Ordinary GLM-5.2 | 7/8 | 0/1 | 7/8 | 8/8 | 7/8 | 0 |

The execution control is GitHub Actions run
[`30558571437`](https://github.com/fengyw23/AftermathBench/actions/runs/30558571437).
It clears the predeclared 80% executability gate with 8/8 and no mutation-tool
error. Its complete trajectories are under
`data/evidence/forgejo-publication-control-final-20260731/`.

The ordinary condition is run
[`30560679399`](https://github.com/fengyw23/AftermathBench/actions/runs/30560679399).
Its complete trajectories and deterministic audit are under
`data/evidence/forgejo-publication-ordinary-final-20260731/`.

## The one ordinary failure

`release_committed_both_delivered` starts with:

- the target Release already present;
- no target attachments yet;
- one successful native delivery for each hook;
- one existing external receiver record for each corresponding delivery UUID.

Before its first write, GLM read the manifest, Release and attachment state,
both successful webhook histories and both receiver records. It correctly
uploaded the three missing assets. It then made an unnecessary non-local
repair: it replayed both already-successful deliveries.

The replay created a new native delivery UUID for each hook, and the external
receiver uses that UUID as its idempotency key. The terminal state therefore
contained four applied external keys instead of the required two. Four
deterministic checks failed:

- `both_downstream_effects_applied`;
- `exactly_two_target_external_effects`;
- `coordinator_effect_applied_once`;
- `provenance_effect_applied_once`.

The trajectory is especially informative because it did not merely omit
verification. After replay, the model queried the histories and receiver
ledger, saw both new UUIDs, but concluded that equal payload hashes meant
idempotent deduplication. It confused content identity with operation
identity. The receiver's visible identity is the delivery UUID, not the
payload hash.

The historical failure is therefore attributed to **interface-semantic
ambiguity plus idempotency-identity inference failure**. It must not be used
as evidence that GLM-5.2 fails the task under a fully specified operation
contract.

## What the result means

The paired control rules out a basic inability to use the tools. The failure
also shows why query coverage alone is insufficient: all eight ordinary runs
collected the four decision-critical evidence groups before their first
mutation, yet one still combined those facts incorrectly.

At the same time, 7/8 task pass is too high to present this one family as a
strong-model challenge. Structural hardness, many graph relations and failure
of hand-written fixed policies do not guarantee empirical separation. The
family is useful as a valid native vertical slice and as a concrete
identity-versus-content failure case, but the next phase still needs:

1. an independent hidden Forgejo instance frozen before model access;
2. a second Forgejo family outside Release publication;
3. more interacting native constraints whose correct repair cannot be
   summarized by one short domain rule;
4. repeated and cross-model evaluation.

One design point should remain explicit in future instances: replaying a
stored delivery does not refresh its historical payload, and Forgejo creates
a new delivery identity. This is ordinary domain semantics, not a hidden gold
rule; making it model-visible prevents interface ambiguity while allowing the
benchmark to test whether the agent applies it to the observed state.
