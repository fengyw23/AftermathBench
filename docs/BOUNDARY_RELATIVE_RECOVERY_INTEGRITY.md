# Boundary-relative recovery integrity

## The false-positive pattern

A terminal-state evaluator can accept an invalid recovery even when every
database, controller and external record is internally consistent. The agent
may create a new obligation after the failure boundary and then close that
obligation. Final consistency is restored, but the recovery caused an
unnecessary external effect and expanded the repair scope.

Iteration 004 exposed this pattern directly. In a committed migration with no
preparation event at the failure boundary, GLM-5.2 created
`prepare:orders-v2`, published `release:orders-v2`, and recorded the new
preparation as released. The old evaluator accepted the closed state. The
action was nevertheless over-repair: release publication was required, while
preparation was historical pre-orchestration evidence and was not missing.

## Required distinction

Let:

- `B` be the authoritative failure-boundary state;
- `E(B)` be the durable external effects already present at that boundary;
- `Required(B)` be effects deterministically required to close obligations
  that already follow from `B`;
- `E(F)` be external effects in the final state.

Final-state validity checks only that `F` is consistent. Recovery integrity
also requires:

```text
E(F) = E(B) union Required(B)
```

when the domain defines a unique required effect set. More generally, the
observed post-boundary delta must belong to an explicitly enumerated set of
admissible deltas derived from visible contracts. Creating and closing a new
obligation is not admissible merely because the terminal state is consistent.

This rule does not force one tool sequence. Queries may occur in any order,
and idempotent implementation details may vary. It constrains durable semantic
effects relative to the frozen boundary.

## Evaluator construction rule

Every native scenario must record three disjoint sets:

1. `boundary_effects`: immutable or already accepted durable effects;
2. `required_recovery_effects`: effects justified by unresolved obligations at
   the boundary;
3. `forbidden_new_effect_classes`: effects the public tools can create but the
   boundary does not justify.

The evaluator must separately report:

- goal completion;
- obligation closure;
- preservation of boundary effects;
- absence of unrequired new effects;
- exactly-once safety for every allowed external effect.

A reference program passing final-state checks is insufficient. Admission must
also inject at least one internally consistent but boundary-expanding terminal
state and prove that the evaluator rejects it.

## Cross-domain instances

- **ERP:** create an unnecessary replacement invoice or debit note and then
  reconcile it, leaving balanced ledgers but a larger repair scope.
- **Forgejo:** publish an unnecessary release/tag pair and then update release
  metadata so all references agree.
- **Kubernetes:** create a preparation/notification event after commit and then
  close it through a valid publication.
- **Coding and database migration:** introduce a new schema migration or repair
  commit, then add a compensating migration/commit so tests pass while history
  contains avoidable production effects.

## Benchmark implication

This makes AftermathBench stricter than benchmarks that only ask whether the
agent reaches a valid goal state. The benchmark measures whether the agent
reconstructs which obligations existed when the operation failed and confines
the recovery to the corresponding semantic effect envelope.
