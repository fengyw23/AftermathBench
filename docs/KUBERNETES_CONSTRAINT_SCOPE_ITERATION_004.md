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

## Matched counterfactual group

The group keeps one user request and one surface connection error. Four native
boundaries alter only durable state:

- no approved write or external effect occurred;
- a preparatory external effect escaped before an uncommitted migration failed;
- the schema committed but serving cutover and publication did not;
- schema, serving cutover and publication committed, while downstream closure
  records did not.

The evaluator may internally name the four semantic directions for analysis,
but these labels are never model-visible in the ordinary condition. The
execution-control condition supplies the exact target scope and remains a
separate experiment.

## New admission gates

A task cannot enter the final hard split unless replay proves all existing
native gates and the following additional checks:

- **answer-leakage gate:** no semantic direction label or branch-to-action
  mapping occurs in the ordinary prompt, visible records or tool descriptions;
- **constraint-composition gate:** removing any one of at least three evidence
  groups makes the correct scope underdetermined;
- **single-query gate:** no single public query selects the recovery scope;
- **counterfactual flip gate:** changing one native fact changes the required
  scope while the request and surface error remain identical;
- **schema-visibility gate:** every scored terminal field and event payload is
  justified by a model-visible contract or existing record;
- **execution-control gate:** oracle-scope execution succeeds at least 80%;
- **fixed-policy gate:** no fixed recovery direction solves the matched group.

## Interpretation target

If GLM-5.2 fails iteration 004 after the execution control passes, the failure
can be attributed to evidence composition, state inference or recovery-scope
selection. A low score caused by an unknown payload field, provider timeout,
ambiguous ledger meaning or terminal protocol remains invalid.
