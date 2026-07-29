# Kubernetes constraint-derived recovery scope: iteration 004

## Decision from iteration 003

Iteration 003 is a valid but easy directional pilot. GLM-5.2 passed all four
ordinary states after the hidden closure conventions were made observable. The
task still states the recovery branches directly in the user instruction and
`recovery-policy`, so it primarily tests state lookup plus runbook execution.
Adding more Kubernetes objects or more mutations would not fix that problem.

Iteration 004 must test whether an agent can *derive* the recovery scope from
independent native constraints. It must not name rollback, compensation,
forward completion or downstream-only repair in the ordinary prompt, policy,
tool descriptions or resource identifiers.

## Model-visible constraint sources

The same native systems remain, but each source contributes only one part of
the decision:

1. a change-authorization record states whether uncommitted writes may proceed;
2. the database catalog states the irreversible schema epoch and migration
   identity;
3. Kubernetes Jobs and Events establish whether migration execution failed or
   committed;
4. Deployments and the Service establish current serving capacity and routing;
5. an external registry establishes which preparation, publication and audit
   effects escaped;
6. event and audit contracts define payload fields and exactly-once keys;
7. preservation records identify the backup, prior release, RBAC and unrelated
   schedule that must survive.

No one object may contain a branch-to-action table. The correct scope must
require at least three sources and at least two interacting rules, such as
"closed authorization forbids an uncommitted candidate" together with
"external preparation requires one compensation", or "committed schema cannot
move backward" together with "the service must have one compatible available
backend".

## Implemented matched counterfactual group

The group keeps one user request and one surface connection error. The four
implemented native boundaries form two single-fact counterfactual pairs:

- the same failed migration Job with no preparation event versus one escaped
  preparation event;
- the same committed schema and completed serving cutover with no release
  publication versus one already accepted publication.

The first pair changes only `prepare:orders-v2`; the second changes only
`release:orders-v2`. These projections are calculated from the replayed
boundary state rather than copied from author labels. All four states contain
a real migration Job and require closure of a change record, release ledger,
recovery audit and external audit event.

The evaluator may internally name the four semantic directions for analysis,
but these labels are never model-visible in the ordinary condition. The
execution-control condition supplies the exact target scope and remains a
separate experiment.

## Implemented admission gates

A task cannot enter the final hard split unless replay proves all existing
native gates and the following additional checks:

- **answer-leakage gate:** no semantic direction label occurs in the rendered
  system prompt, complete ordinary initial message, successful prefix trace,
  identifiers, failure result, visible contracts or tool descriptions;
- **constraint-composition gate:** every reference scope cites at least three
  independently queryable evidence groups and two visible constraints;
- **single-query gate:** no single public query selects the recovery scope;
- **counterfactual flip gate:** changing one native fact changes the required
  scope while the request and surface error remain identical;
- **schema-visibility gate:** every scored terminal field and event payload is
  justified by a model-visible contract or existing record;
- **execution-control gate:** oracle-scope execution succeeds at least 80%;
- **fixed-policy gate:** no fixed recovery direction solves the matched group.

The current composition gate validates provenance and minimum composition. It
does not yet prove, by automated ablation, that deleting each cited source
makes the answer underdetermined. That stronger minimal-evidence test remains
required before this mechanism is treated as a frozen benchmark template.

## Current implementation status

The repository now contains the native prefix, four fault injectors,
constraint-only model interface, deterministic evaluator, public-tool
reference recovery, six fixed policies, replay graph, prompt audit and GitHub
Actions workflows for native replay and model experiments.

The final native replay (GitHub Actions run `30455470248`, source commit
`4613d1207d196fa877efb543c0274ac8bdd102cf`) admitted the scenario as `hard`:

- all four public-tool reference recoveries passed;
- all 26 semantic relations were observed by real-cluster replay;
- the six fixed policies achieved at most 25% per-state success and none solved
  the four-state matched group;
- the complete ordinary input audit covered 13 rendered surfaces and found no
  recovery-direction label leak;
- the replay-derived graph contains 26 relevant entities, 26 edges, 25
  relation types and dependency depth 6.

The immutable evidence is archived under
`data/evidence/kubernetes-constraint-native-final-20260729/`. This admission
establishes task validity; model difficulty is reported separately and cannot
be inferred from admission alone.

The first execution-control experiment subsequently exposed underspecified
external-event payload and record-update rules. Commit `562f604` made those
rules model-visible and increased the per-response provider timeout. Because
this changes an audited input surface, the corrected task received a fresh
real-cluster admission in GitHub Actions run `30458653113` at commit
`a385e39540dd6c9693881c31c053f16a804fd640`. It again passed all admission
checks, all four references, the zero-leak 13-surface audit and the fixed-policy
gate. The corrected evidence under
`data/evidence/kubernetes-constraint-native-corrected-20260729/` supersedes the
earlier archive for iteration 004.

Ordinary-model auditing later found that a terminal-consistent state could
manufacture a preparation event after the failure boundary and still pass.
Commit `69d5373` added the visible boundary-relative external-effect rule and a
deterministic rejection check. The resulting final admission, GitHub Actions
run `30470729491`, again passed hard admission, 4/4 references, zero leakage
and the fixed-policy gate. Its evidence under
`data/evidence/kubernetes-boundary-relative-admission-final-20260730/`
supersedes all earlier iteration-004 admission archives.

## Interpretation target

If GLM-5.2 fails iteration 004 after the execution control passes, the failure
can be attributed to evidence composition, state inference or recovery-scope
selection. A low score caused by an unknown payload field, provider timeout,
ambiguous ledger meaning or terminal protocol remains invalid.
