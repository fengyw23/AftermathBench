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

A frozen repeated ordinary experiment combines primary run `30521275565` with
one infrastructure-only retry from run `30525931977`. The provider disconnected
before returning one trajectory in the primary run; that missing cell was
rerun from the same failure boundary and excluded from the score rather than
counted as a model failure.

The resulting 20 valid trajectories score 13/20 (65%) with 0/5 matched-group
success. Goal completion, repair completeness, and preservation are 20/20;
protocol safety is 13/20. Every failure created a duplicate replacement invoice
that already existed at the failure boundary, and every failed trajectory
omitted the linked-invoice query. There were zero model tool-call errors. The
complete raw primary and retry artifacts, selection rule, independent analysis,
and byte-level manifest are archived under
`data/evidence/erpnext-sales-return-ordinary-repeat5-20260730`.

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

Replacement control run `30522367760` uses the corrected evaluator and passes
12/13 states (92.31%), above the pre-registered 80% gate. Independent analysis
and deterministic rescore agree on all 13 outcomes. There are no provider,
runtime, tool, external-key, or protocol errors.

The one failure is genuine. In `state_02`, the supplied scope required
compensating the accepted preparation and discarding the failed candidate. The
model emitted the compensation and audit events and repaired the ledgers, but
left the candidate Deployment and Secret in place. Full hash-bound evidence is
archived under
`data/evidence/kubernetes-interaction-control-valid-20260730`.

Because the gate passed, primary ordinary run `30527525012` was launched from
the exact same source commit
`54e48ab0b0686f103dd1b33b780401d6f2d0a64f`. It produced 11 valid
trajectories; `state_01` and `state_02` each exhausted three non-streaming
provider attempts without producing a trajectory. Those empty provider
failures were excluded rather than scored as model errors.

Infrastructure-only retries completed the matrix. Extended-timeout run
`30540796138` produced `state_02`; a preserved non-streaming retry
`30543847725` still failed to produce `state_01`; and SSE-streaming run
`30549370454` produced `state_01`. The scenario, prompt, public tools, failure
boundaries, and evaluator did not change.

Fresh kind clusters have different runtime-generated `kube-root-ca.crt`
certificates. After excluding that non-task ConfigMap and its derived raw
fingerprint, the control and every ordinary retry have the same task-state
projection SHA-256:
`0d874013374de673660bad82e7b8330d5d4c88dd529455a377c4478328a9dfca`.

The selected ordinary matrix passes 1/13 (7.69%) with 0 matched-group success,
compared with the execution control's 12/13 (92.31%), an absolute difference
of 84.62 percentage points:

| Component | Explicit scope | Ordinary |
|---|---:|---:|
| Goal Completion | 12/13 | 8/13 |
| Repair Completeness | 13/13 | 1/13 |
| Preservation | 13/13 | 12/13 |
| Protocol Safety | 13/13 | 7/13 |
| Recovery Integrity | 12/13 | 1/13 |

All 13 ordinary trajectories queried all six registered evidence groups and
ended normally with `model_stopped`. Independent analysis classifies all 12
failures as scope failures; deterministic rescore changes zero outcomes.
Thus the observed gap is not explained by hidden evidence, inability to call
the tools, a termination protocol, or the repaired scalar-type ambiguity. The
complete primary, retry, selected, analysis, and rescore artifacts are under
`data/evidence/kubernetes-interaction-ordinary-composite-20260730`.

## Evidence portability

Hash-bound JSON, Markdown, and text evidence now uses repository-enforced LF
line endings. The manifest builder records explicit exclusions so metadata
that refers to the manifest cannot create a circular hash dependency.

The final full test suite passes:

```text
385 passed; 1 skipped
```

## Resume decision

The methodology-validation phase is closed:

1. ERPNext repeated evidence is archived and byte-verified.
2. The corrected Kubernetes execution control passes its pre-registered gate.
3. The ordinary Kubernetes condition has 13 selected valid trajectories.
4. Control and ordinary task-state projections are identical.
5. Deterministic rescore changes zero selected outcomes.
6. Provider failures are preserved but excluded from the score.
7. Complete selected and raw evidence is secret-scanned and archived.

The broader benchmark goal may resume from this checkpoint. The current
Kubernetes family remains a development stress test, not a formal release
case, and one trial per matched state is not a leaderboard estimate.
