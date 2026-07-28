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

- at least 6 successful prefix writes;
- at least 3 protected persistent prefix effects;
- at least 4 relation types;
- dependency depth of at least 4;
- at least 3 independent evidence groups;
- the reference recovery must actually use all 3 evidence groups;
- no single boundary query may determine every required action;
- at least 2 boundary query groups must be required;
- every semantic relation must have replay evidence in a native field or
  audit record;
- at least 3 mutations in the shortest valid recovery;
- at least 2 downstream dependencies repaired;
- at least 2 executable actions that are unsafe in some matched variant;
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

The current native result is one ERPNext procurement-return family with a
development instance and a pre-model-frozen holdout instance. It establishes
an executable hard-task construction method; it is not yet a multi-domain
benchmark release.
