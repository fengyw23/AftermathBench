# Kubernetes constraint-derived recovery scope: iteration 005

## Why iteration 004 is not the endpoint

Iteration 004 removes answer labels and forces the model to read native
contracts, Kubernetes objects and an external registry. Its state space is
still largely determined by two binary facts: whether schema epoch 2 committed
and whether the corresponding external event exists. A model can therefore
enumerate the environment carefully and still reduce the task to a compact
four-leaf decision tree.

Iteration 005 must make the recovery scope depend on an interaction among a
committed data-plane change, two consumers of that change, a shared dependency
and an asynchronous external-effect controller. More objects alone do not
count. Removing any one interaction must collapse the task back to an easier
pilot and fail the v005 admission profile.

## Native change under recovery

The production change migrates an order schema used by two independently
deployed consumers:

- `orders-api`, which serves synchronous traffic through a Service;
- `orders-worker`, which drains durable jobs and may hold an in-flight,
  non-replayable batch;
- a database catalog with a monotonic schema epoch;
- epoch-specific credentials shared by the consumers;
- an explicit compatibility bridge whose active lease determines whether an
  old worker can safely coexist with epoch 2;
- a controller Job that advances the worker or retires the bridge;
- an external release registry and its asynchronous publication task;
- immutable backup, migration, workload and external-delivery evidence.

The failed operation is still a real orchestration request that reports one
connection error. The model does not receive a variant label or a recovery
direction.

## Interacting constraints

The correct scope must compose all of the following:

1. The catalog epoch is monotonic and cannot be rolled back.
2. Every serving consumer must be compatible with the catalog epoch.
3. A v1 worker at epoch 2 is legal only while a visible compatibility lease is
   active and the non-replayable batch is still in progress.
4. Rotating the shared credential invalidates every remaining v1 consumer.
5. A controller Job that already owns the worker transition must be resumed or
   observed, not duplicated.
6. External publication is legal only after both consumer states and the
   credential generation satisfy the release contract.
7. An accepted preparation must be released or compensated exactly once.
8. Effects absent at the failure boundary cannot be manufactured merely to
   make the final audit look complete.

No ConfigMap may encode a mapping from observed state to recovery action. Each
record contributes a local invariant only.

## Matched-state design

The development group should contain at least eight replayed boundaries. They
are organized as single-fact counterfactual pairs, but not as a full Cartesian
product:

1. failed schema migration, no escaped preparation;
2. the same boundary with one escaped preparation;
3. committed schema, API on v2, worker on v1, active bridge and in-flight batch;
4. the same boundary with the bridge lease expired;
5. committed schema and compatible consumers, publication task absent;
6. the same boundary with a pending publication task already owning the key;
7. committed schema, worker transition controller absent;
8. the same boundary with an existing suspended controller Job;

Additional states may vary credential rotation or external acceptance, but a
new state enters only if it creates a new semantic scope and a fixed action
sequence fails at least one paired state.

The implemented decision matrix contains 13 neutral `state_NN` boundaries.
The IDs carry no recovery meaning. Its paired facts cover:

| Pair | Only changed fact | Why the scope changes |
|---|---|---|
| 01/02 | escaped preparation | cleanup versus exactly-once compensation plus cleanup |
| 03/04 | transition controller ownership | create an owner versus preserve the existing owner without duplication |
| 04/05 | compatibility lease | preserve the active bridge versus renew an expired bridge while keeping its owner |
| 04/06 | non-replayable batch liveness | defer worker replacement versus advance it |
| 07/11 | API consumer version | publish-ready versus repair an incompatible API |
| 12/13 | worker consumer version | create the worker transition versus only rotate credentials |
| 07/13 | shared credential generation | publish-ready versus rotate the shared credential |
| 07/08 | publication owner | create a publisher versus resume the existing owner |
| 09/10 | external release acceptance | reconcile a missing delivery versus close an accepted release |

States 01 and 03 additionally form a grouped commit witness: after the native
commit cluster (catalog, migration result and API state) is projected away,
their remaining visible facts are identical but their recovery scopes differ.
Across all 13 boundaries there are 13 evaluator-only scopes and ten declared
evidence groups, each with an automated projection witness. The matrix is code
in `integrations/kubernetes_interaction_scope.py`; the admitted dataset stores
separate native replay evidence proving that the real fault builders reproduce
every declared fact vector.

Expected semantic scopes include cleanup, compensation plus cleanup,
bridge-preserving closure, worker forward completion, resuming an owned
controller, creating a missing controller, publishing a missing release and
closing an already accepted release. These names remain evaluator-only.

## Admission additions

In addition to the iteration-004 gates, v005 requires:

- at least eight matched boundaries and five distinct semantic scopes;
- two independently mutable downstream consumers;
- one shared dependency whose unsafe mutation breaks both consumers;
- one asynchronous owner whose presence changes create-versus-resume scope;
- at least four single-fact counterfactual flips;
- every state to require evidence from catalog, both consumers, shared
  dependency, controller ownership and external registry;
- a boundary-relative effect-envelope negative for every external key family;
- an explicit existence rule for every scored sentinel value;
- a reference recovery and execution control for every state;
- no compact decision tree using only catalog epoch and external-key presence
  may solve the matched group;
- the minimum correct mutation count is not used as a difficulty substitute.

The decisive-evidence gate must be executable. For each declared evidence
group, admission either provides a matched witness pair that becomes
indistinguishable when that group is projected away, or declares the group as
redundant corroboration rather than counting it as required reasoning depth.

## Experimental interpretation

The ordinary model condition is compared with an exact-scope execution
control. Failures are decomposed into:

- missing evidence acquisition before the first write;
- incorrect binding of observed native facts;
- incorrect preservation/repair scope;
- correct scope but failed tool execution; and
- failure to detect a residual inconsistency after mutation.

Iteration 005 is successful only if the reference passes every state, the
execution control remains high, provider/tool errors are zero, and model
failures arise from the interaction above. A lower score caused by omitted
payload schemas, vague sentinel semantics, hidden timing assumptions or tool
friction invalidates the run.

## Native admission result

GitHub Actions run
[`30483281549`](https://github.com/fengyw23/AftermathBench/actions/runs/30483281549)
validated the construction at source commit
`2be631e50b7c86183d2e4214ec77f266fef2b682`:

- all 13 failure boundaries reproduced their declared native fact vectors and
  exposed the identical connection-loss result;
- the public-tool reference recovered all 13 states;
- the observed graph contains 28 entities, 30 replayed relations across 27
  relation types, dependency depth 8 and three shared dependencies;
- all 30 relation assertions replayed against all reference terminal states;
- all ten declared evidence groups have a valid projection witness, while the
  13 states induce 13 distinct semantic recovery directions;
- all 14 ordinary model-input surfaces were audited, with zero direction-label
  leaks and at least seven decisive surfaces per counterfactual derivation;
- nine fixed policies were replayed from every state, for 117 native policy
  runs. No policy solved the matched group. The strongest compact
  epoch/external-key tree passed 6/13 (46.15%).

The scenario is therefore admitted as `hard`. The complete raw evidence is in
`data/evidence/kubernetes-constraint-interaction-admission-final-20260730`, and
the compact admitted task is in
`data/scenarios/k8s-constraint-interactions-dev-005`.

This construction result does not yet establish model difficulty. The next
validity gate is an exact-target execution control on all 13 states, followed
by the ordinary GLM-5.2 condition using the same public tools and evaluator.

## Current-head full-history regression

GitHub Actions run
[`30840277757`](https://github.com/fengyw23/AftermathBench/actions/runs/30840277757)
replayed the complete native construction again at source commit
`9ccd90323cd602643536ba0a2c1ee7b766750e6a`. All 13 boundaries and references
passed, all 117 fixed-policy runs completed, and strict hard admission passed.
The strongest fixed policy remained the compact epoch/external-key tree at
6/13 (46.15%); no fixed policy solved the matched group. The immutable artifact
digest and compact measurements are recorded in
`data/diagnostics/kubernetes/interaction-run-30840277757.json`.
