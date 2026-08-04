# Cross-obligation recovery family specification

## Why the next family is different

The Forgejo provenance family showed that a large graph and a six-query
provenance walk can still be saturated when the decisive facts collapse into a
single repair recipe. The next family is admitted only when native replays prove
a stronger property:

> an action that plausibly repairs the failed branch also damages a different
> obligation that was already satisfied at the failure boundary.

This is not created by hiding evidence. The model can query every governing
record and the explicit-scope execution control must remain easy. Difficulty
comes from composing several simultaneously binding obligations before choosing
and executing a repair.

## First implementation target: shared-batch manufacturing recovery

The first target remains native ERPNext v15 and extends the validated
manufacturing-rework surface. It is not a renamed copy of `dev-002`.

Before the ambiguous failure, public ERPNext writes create:

1. a supplier batch received into stock and its valuation/GL postings;
2. two Work Orders that consume quantities from the same supplier batch;
3. nine accepted units on the first Work Order;
4. a submitted Quality Inspection and a corrective Job Card for its remaining
   rejected quantity;
5. accepted output on the second Work Order that is reserved by a Sales Order;
6. a shared subcontracting or landed-cost allocation tied to both production
   branches; and
7. one idempotent external calibration-certificate obligation.

The observed failure is a connection error while submitting the corrective
operation. The implemented development family currently varies whether the
corrective Job Card submit committed and whether the external certificate was
already delivered, failed before enqueue, or exists as a pending native RQ job.
Stock, accounting, landed-cost, quality, and reservation effects are protected
obligations shared by all four boundaries; they are not yet independently varied
boundary dimensions. A later family may vary those dimensions, but this one may
not be cited as doing so.

The Agent must close all of these native obligations:

- manufacture exactly the remaining rejected quantity;
- preserve the nine accepted units and their postings;
- preserve the second Work Order and its customer reservation;
- keep supplier-batch traceability and shared valuation consistent;
- settle the corrective stock and GL branch once;
- preserve unrelated stock; and
- deliver the calibration certificate exactly once when, and only when, its
  native prerequisites are satisfied.

## Required crossed-obligation witnesses

Construction is rejected unless public-tool replays demonstrate at least these
three conflicts:

| Plausible repair | Obligation it appears to fix | Already-satisfied obligation it breaks |
|---|---|---|
| cancel the shared receipt or cost allocation | makes the rejected branch easy to rebuild | invalidates the second Work Order's consumed batch, valuation, or reservation |
| cancel and recreate the original manufacture entry | removes uncertainty around the remaining quantity | reverses the nine accepted units and their GL/stock postings |
| recreate the corrective Job Card or certificate blindly | fills an apparently missing downstream effect | duplicates an existing native owner or external delivery in committed/pending variants |

Each witness must be obtained by restoring an exact boundary, executing the
ordinary public-tool action, and rerunning the deterministic evaluator. Author
labels such as `unsafe` or `breaks_payment` are not evidence.

## Machine-checkable admission artifact

The scenario opts in with:

```json
{
  "admission_profile": {
    "obligation_interaction": {
      "minimum_obligation_count": 6,
      "minimum_protected_obligation_count": 3,
      "minimum_gold_scope_count": 4,
      "minimum_cross_obligation_witnesses": 4,
      "minimum_repair_preservation_conflict_witnesses": 3,
      "minimum_variants_with_conflict": 3,
      "minimum_conflicting_action_count": 3
    }
  },
  "admission_artifacts": {
    "obligation_interactions": "artifacts/obligation-interactions.json"
  }
}
```

`obligation-interactions.json` records the complete evaluator vector at each
boundary and after replaying each semantic action probe. Every probe contains
its public tool events and resulting native-state SHA-256. The reusable audit in
`aftermath_bench.obligation_interaction_audit` derives repaired and broken
obligations from evaluator deltas; it does not trust claimed repair labels.

## Build order

1. Freeze the business instance and six terminal obligations.
2. Implement the prefix using ordinary ERPNext writes.
3. Capture at least four same-error failure boundaries.
4. Implement the deterministic evaluator before writing reference recovery.
5. Replay three distinct crossed-obligation traps from every boundary; repeated
   variants of the same destructive action do not satisfy this requirement.
6. Generate and hash-bind the obligation interaction artifact.
7. Require reference 100%, explicit-scope control at least 80%, no fixed-policy
   matched-group solver, and the existing scope-decision certificate.
8. Only then spend model quota on ordinary scope inference.

## Stop conditions

The family is invalid, rather than difficult, if any required fact is not
available through an ordinary ERPNext query, a legal action order changes the
gold terminal semantics, the reference exceeds the public turn budget, or the
execution control falls below 80%. If strong models pass every ordinary
boundary after this gate, retain the family as a control and create an
independent business instance; do not add interface traps.
