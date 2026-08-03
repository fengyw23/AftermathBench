# Benchmark Specification

## Research question

When a long tool workflow has already produced persistent side effects and a
later operation returns an ambiguous failure, can an agent reconstruct what
actually happened, repair the complete affected dependency subgraph, preserve
valid prior effects, and restore global consistency?

## Formal setting

An action changes the environment according to:

```text
S[t+1] = T(action, S[t], hidden transition outcome)
observation = O(S[t], action, S[t+1])
```

A timeout or server error does not identify the hidden transition outcome. The
same observation may mean that the action:

- did not commit;
- committed but lost its response;
- committed only a subset of writes;
- scheduled an asynchronous transition that is still pending.

## Hard-task admission gate

For a native task family to enter the hard split, every claim below must be
derived from a replayed prefix, failure boundary, reference recovery, or fixed
baseline. Author-written complexity numbers do not count.

- at least 8 successful prefix writes;
- at least 3 protected persistent prefix effects;
- at least 20 relevant native entities and 8 relation types;
- dependency depth of at least 5;
- at least 4 independent evidence groups;
- the reference recovery must actually use all 4 evidence groups;
- no single boundary query may determine every required action;
- at least 2 boundary query groups must be required;
- every semantic relation must have replay evidence in a native field or
  audit record;
- at least 4 mutations in the shortest valid recovery;
- at least 2 downstream dependencies repaired;
- at least 2 protected shared dependencies;
- at least 3 executable actions that are unsafe in some matched variant;
- at least 3 independent action branches, with at least 2 varying across
  matched variants;
- at least 3 distinct recovery signatures;
- every fixed heuristic must remain below 50% task pass; and
- every fixed heuristic must have zero matched-group success.

The reference recovery must pass every matched variant. Counts refer only to
the task-relevant recovery graph; unrelated rows, tools, and documents cannot
satisfy the gate. Entity and edge counts are reported as descriptive
statistics rather than used as arbitrary difficulty thresholds.

## Evaluation

The primary score is `Recovery Integrity Pass`.

Its components are:

- `goal_completion`: the remaining user goal is achieved;
- `repair_completeness`: cross-record, ledger, queue, and external effects are
  closed with no failed or pending residue;
- `preservation`: protected effects from the successful prefix remain valid;
- `protocol_safety`: no duplicate, forbidden, or unsafe side effect occurred.

The benchmark also reports matched-fault-group success, component-wise pass
rates, dangerous-action counts, and clean-to-recovery gaps.

## Controls

Each base workflow must provide:

- a state-driven reference recovery using only public tools;
- an explicit-scope execution control that supplies the correct recovery scope
  but still executes through the same public tools;
- fixed heuristic baselines from the same failure snapshots; and
- the full recovery task exposing only ordinary tools and the common
  ambiguous error.

This separates task construction and tool-execution failures from
investigation, state diagnosis, recovery-scope, execution, and verification
failures.

## Current release boundary

The current partial release contains three fully bound public-development
slots, one in each native domain:

- ERPNext sales-return, exchange and reconciliation: 4 variants;
- Forgejo multi-consumer release publication: 8 variants;
- Kubernetes constraint-interaction recovery: 13 variants.

All three pass structural and runtime admission, reference replay,
fixed-policy rejection, artifact-hash verification, seven-role evidence
sealing, and a supplied-scope execution control of at least 80%. Together they
contain 25 formal cases. The implementation now covers all 12 target families;
10 are hard-admitted, but only these three have complete release evidence.
Easy pilots, candidate-tier scenarios, consumed development instances and
model-saturated scenarios remain excluded from formal claims.

The target matrix no longer multiplies every instance by one global four-state
list. Each family declares its own required variant count, producing 183
planned cases across 36 instances. Two independently frozen hidden lifecycles
have been consumed as methodology evidence: Forgejo publication test-002 and
ERPNext manufacturing test-003. Neither is reused or treated as an unconsumed
leaderboard slot, so no formal hidden-test slot currently exists. The ERPNext
test-003 run completed all four trajectories without infrastructure errors,
with 75% task pass and 0% matched-group success. `python -m aftermath_bench
status` and
`python -m aftermath_bench validate-release` derive this boundary from the
matrix, scenario identities, admission artifacts, runtime evidence, hashes,
and execution-control summaries.
