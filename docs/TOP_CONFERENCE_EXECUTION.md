# Top-conference benchmark execution plan

## Research question

After a step in a long-running agent workflow returns an error, can the agent
interact with the real system to reconstruct the post-error state, identify
which effects and downstream obligations already exist, and complete a repair
that is neither destructive nor incomplete?

The benchmark does not assume that the failed operation was a write, that the
request definitely reached the server, or that rollback is the right repair.
An error can correspond to no durable effect, a committed primary effect, a
missing downstream effect, or an asynchronous continuation that is still
pending.

## What is executable today

The repository currently contains one ERPNext purchase-return family with a
public development instance and a frozen historical holdout instance. Both
instances have four matched post-error states and deterministic terminal-state
evaluation.

The family now has:

- a one-hop relation query that exposes native ERPNext link fields without
  returning a hidden graph or recommended action;
- a tool-provenance manifest for every model-visible read, write, and runtime
  control;
- executable relation assertions replayed over captured native evidence;
- 21 relevant entities, 23 replayed relations, 13 relation types, dependency
  depth 7, four evidence sources, and four distinct recovery signatures;
- reference recovery, fixed baselines, component-level evaluation, and raw
  model trajectories.

Under Hard Admission v2 the family is classified as `candidate`, not `hard`.
It passes every structural and evidence gate, but one matched state requires
only three state-changing operations. The formal hard split requires at least
four in every state. This status is intentional: historical model scores are
not used to override a failed construction gate.

## Hard Admission v2

A formal hard family must satisfy all of the following from executable
artifacts:

- at least eight task-relevant successful prefix writes;
- at least 20 relevant native entities and eight relation types;
- dependency depth at least five;
- at least four independent evidence sources;
- all counted relations replay successfully from native evidence;
- no single query identifies every matched state;
- at least four state-changing recovery operations in every state;
- at least two downstream repairs and two protected shared dependencies;
- at least three dangerous but executable incorrect plans;
- at least three distinct semantic recovery signatures;
- variation across at least two independent action branches;
- reference recovery passes every state;
- fixed heuristics do not solve the matched group.

The graph file can no longer satisfy admission with an author-written
`observed: true`. Each edge must contain selectors and deterministic
assertions, and each assertion is replayed across all captured states.

## Dataset matrix

`data/benchmark_matrix.json` fixes the target portfolio:

- ERPNext, Forgejo, and Kubernetes;
- four task families per domain;
- one public development instance and two hidden instances per family;
- four matched post-error states per instance;
- 144 executable cases in total.

Every family declares a real native operation that reports an error, the
native objects involved, protected prior effects, at least two independent
downstream branches, and at least three expected recovery signatures. The
matrix validator prevents silent scale drift and simple one-state or
one-branch tasks from being counted toward the release target.

## Immediate build order

1. Re-run the ERPNext candidate with the repaired one-hop query and separate
   interface errors from recovery errors.
2. Implement the ERPNext sales-return/exchange family as the first formal hard
   family, using a different downstream structure from purchase returns.
3. Add the manufacturing-rework and multi-warehouse-transfer families.
4. Freeze the generic native-family runner and evidence schema.
5. Implement Forgejo and Kubernetes runtimes against their public APIs and
   native audit records.
6. Freeze private test instances before any main-model evaluation.

The release target remains 144 cases, but a family enters the formal score
only after its reference program, execution control, evidence replay, reset,
and hard-admission checks all pass.
