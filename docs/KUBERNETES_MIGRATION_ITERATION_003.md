# Kubernetes schema-rollout recovery: iteration 003

## Why this iteration exists

The preceding settlement tasks varied the amount of durable work left behind,
but every valid recovery still moved in the same semantic direction: preserve
successful effects and forward-complete the missing suffix. GLM-5.2 therefore
solved all four states after the evaluator ambiguity was removed. More objects
and more edges did not by themselves create a harder recovery decision.

Iteration 003 changes the matched group itself. The same surface error can now
require one of four objectively different recovery directions:

| Boundary evidence | Required direction |
|---|---|
| Schema epoch 1; no external preparation escaped | rollback to stable v1 |
| Schema epoch 1; failed migration; preparation event escaped | compensate the external preparation and restore v1 |
| Schema epoch 2; traffic still on v1; no release publication | forward-complete v2 cutover |
| Schema epoch 2; v2 traffic and release publication committed | repair downstream records only |

The direction is not stored as a hidden variant label. It is derived from the
database catalog, migration Job status, Service selector and external registry
records, then checked against a model-visible `recovery-policy` ConfigMap.

## Native state and failure construction

The prefix is created through real Kubernetes writes and includes two
Deployments, a Service, two Secrets, RBAC, an immutable schema catalog, release
and audit records, an unrelated CronJob and a completed backup Job. A prior v1
publication is written to the same open-source idempotent receiver exposed to
the agent.

The ambiguous operation then performs one of four durable subsets before
returning the identical connection-loss error. The model never receives the
variant identifier. It must query ordinary Kubernetes objects, controller
state, Events and receiver records.

## Deterministic evaluation

The evaluator derives the required direction from a read-only capture of the
failure boundary. It checks:

- the correct serving version and capacity;
- candidate resources retained or removed according to the visible policy;
- migration Job identity and terminal evidence preserved;
- ledger, recovery audit and external events closed consistently;
- every external key attempted exactly once;
- catalog, policy, backup, stable identity, RBAC and unrelated schedule
  preserved from the boundary.

The boundary capture is evaluator evidence, not an authored answer. In
particular, the evaluator records native UIDs and policy/catalog data before the
agent acts, so deleting and recreating a protected object cannot pass merely by
reusing its name.

## Admission changes

Hard admission now records semantic recovery directions separately from tool
signatures. A task cannot claim directional diversity merely because four
references used different numbers of `patch_object` calls.

Evidence groups can also be scoped by tool arguments. Reading
`list_objects(resource=configmaps)` no longer automatically proves that the
reference investigated Deployments, Services and Jobs just because all reads
share the same generic tool name.

The replay graph contains 22 relevant entities, 26 executable relations, 25
relation types, dependency depth 11 and four required semantic directions.
GitHub Actions run `30443406478` replayed the complete native experiment at
commit `cf2e649`: all four references passed, the semantic prefix had one
stable hash, the maximum fixed-policy pass rate was 25%, no fixed policy solved
the matched group, and replay-derived hard admission passed every check.

The admitted artifact additionally records 16 successful prefix writes, four
protected effects, six evidence groups in every reference trajectory, at least
four boundary query groups, at least four repair mutations, at least three
downstream repairs and three varying action branches. These are observed replay
properties, not author-entered difficulty labels.

## Validity order

The experiment order is intentionally strict:

1. deterministic unit and schema tests;
2. four native failure boundaries with a common surface error;
3. four public-tool reference recoveries;
4. six fixed policies across all four states;
5. replay-derived hard admission;
6. execution-control model run;
7. ordinary GLM-5.2 run.

Model scores are not interpreted until stages 1–5 pass. A low score caused by
an invisible convention, nonfunctional tool or unstable controller is invalid.
