# Methodology validation checkpoint — 2026-07-30

## Purpose

This checkpoint closes the methodology-validation phase before broader
benchmark expansion resumes. It records which experiments are scientifically
usable, which are excluded, and which gates must be satisfied before an
ordinary-condition result can be interpreted as recovery reasoning.

The repository remains development-only. No current scenario is a formal
public-development or hidden-test release case.

## Current implementation boundary

The machine-readable repository status contains:

- 8 implemented scenarios;
- 41 matched post-error states;
- 4 structurally hard-admitted scenarios;
- 4 hard scenarios on execution-admitted native runtimes;
- 0 formal release scenarios.

The admitted native runtimes are ERPNext, Forgejo, and Kubernetes.
EnterpriseOps remains a prototype only because its service implementation and
native transaction behavior are not available for source and execution audit.

## Scientific protocol

A model result is accepted only when all of the following hold:

1. The failure boundary is replayable from successful native writes.
2. Necessary evidence is available through ordinary public tools.
3. A deterministic reference recovery passes every matched state.
4. An explicit-scope execution control shows that the same model can execute
   the required state changes with the same tools.
5. The control and ordinary conditions use the same source commit, scenario,
   model, prefix state, variant set, evaluator, and public tools.
6. Provider, runtime, and tool-interface errors are zero.
7. Complete sanitized trajectories and failure reports are retained with
   byte-stable SHA-256 manifests.
8. Evaluator requirements are present in the public task contract. A hidden
   representation convention is an evaluator defect, not a model failure.

The ordinary condition is evaluated on durable terminal state. Investigation
and verification behavior is used for failure attribution, not as a hidden
required action sequence.

## ERPNext sales-return evidence

The first valid paired experiment used one run per hidden state at source
commit `9e2760a253c41351313f580de3c511cfac6125b3`:

| Condition | GitHub run | Recovery Integrity | Infrastructure/tool errors |
|---|---:|---:|---:|
| Explicit-scope execution control | `30518617941` | 4/4 | 0 |
| Ordinary recovery | `30519698310` | 2/4 | 0 |

Both ordinary failures completed the business goal but created a duplicate
replacement invoice. One failed to query a pre-existing downstream invoice;
the other failed to refresh invoice state after submitting a Delivery Note
whose native hook created the invoice. This is evidence for recovery-time
state invalidation rather than failure to use the mutation tools.

A frozen repeated ordinary run, `30521275565`, evaluates all four states five
times. Its result must be archived and audited before it is used to estimate a
pass rate.

## Kubernetes interaction evidence

The 13-state constraint-interaction family has already passed native
construction admission:

- reference recovery: 13/13;
- replayed semantic relations: 30/30;
- evidence projection witnesses: 10/10;
- prompt recovery-direction leaks: 0;
- best fixed policy: 6/13, with no fixed-policy matched-group solver.

GitHub run `30518023055` is excluded as the official execution control even
though it passed the pre-registered 80% workflow gate. Its original evaluator
score was 11/13, but one reported failure accepted JSON string `"2"` and
silently rejected the semantically equivalent JSON number `2`. The public
contract named the fields but did not prescribe JSON scalar types.

After contract-scalar normalization, the same terminal state passes and the
deterministic rescore is 12/13. The remaining failure is genuine: the model
did not remove candidate Deployment and Secret objects required to be absent
by the supplied discard scope. The original trajectories, original score, and
corrected rescore are preserved under
`data/evidence/kubernetes-interaction-control-invalid-scalar-20260730`.

Replacement control run `30522367760` uses the corrected evaluator. The
ordinary condition must not be launched unless this replacement:

- completes all 13 states;
- achieves at least 11/13 Recovery Integrity;
- has zero provider, runtime, tool-interface, or contract ambiguity failures;
- survives trajectory-level audit.

If the gate passes, the ordinary branch must point to the exact same source
commit as the replacement control.

## Evidence portability

Hash-bound JSON, Markdown, and text evidence now uses repository-enforced LF
line endings. The manifest builder records explicit exclusions so metadata
that refers to the manifest cannot create a circular hash dependency.

The full test suite at this checkpoint passes:

```text
374 tests passed; 1 skipped
```

## Resume condition

The broader benchmark goal should resume only after:

1. the ERPNext repeated run is downloaded, secret-scanned, analyzed, and
   archived;
2. the replacement Kubernetes control is audited;
3. a Kubernetes ordinary run is launched only if the corrected control gate
   is valid;
4. all accepted control/ordinary pairs are compared by machine-readable
   checks;
5. this checkpoint is updated with final run IDs, pass rates, component
   failures, and archive paths.

