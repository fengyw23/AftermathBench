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

Every released task must satisfy all of the following:

- at least 6 successful prefix writes;
- at least 2 systems or applications;
- at least 3 protected persistent prefix effects;
- at least 20 task-relevant entities;
- at least 28 typed semantic relations;
- at least 4 relation types;
- dependency depth of at least 4;
- at least 2 interacting nonlinear motifs;
- at least 3 commit-state hypotheses behind the same surface error;
- at least 3 distinguishing authoritative evidence sources;
- at least 3 mutations in the shortest valid recovery;
- at least 2 downstream dependencies repaired;
- at least 1 action that is unsafe to retry blindly.

Counts refer to the task-relevant recovery graph. Unrelated rows, tools, and
documents cannot satisfy the gate.

## Evaluation

The primary score is `Recovery Integrity Pass`.

Its components are:

- `goal_completion`: the remaining user goal is achieved;
- `integrity`: cross-record and cross-system invariants hold;
- `repair_completeness`: no failed or pending recovery residue remains;
- `preservation`: protected effects from the successful prefix remain valid;
- `protocol_safety`: no duplicate, forbidden, or unsafe side effect occurred.

The benchmark also reports matched-fault-group success, component-wise pass
rates, dangerous-action counts, and clean-to-recovery gaps.

## Controls

Each base workflow must provide:

- a clean execution control;
- a privileged-state control that reveals the true transition outcome;
- a full recovery task exposing only ordinary tools and the ambiguous error.

This separates base task execution failures from state diagnosis and recovery
failures.

