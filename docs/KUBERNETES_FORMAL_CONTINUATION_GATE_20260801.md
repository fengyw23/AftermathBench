# Kubernetes formal-continuation gate -- 2026-08-01

## Purpose

This checkpoint records why the paused long-running goal was initially blocked
and the evidence that now permits it to resume with the Kubernetes formal
public-development slice. It audits the runtime against the repository's
exact-boundary evidence contract and keeps every later model run behind a
provider-free input lock.

The high-level goal remains correct. K0--K3 are now complete. The next valid
implementation step is K4 execution control; an ordinary-condition model run
or release-slot binding is still premature.

## Current verified position

- ERPNext has the first repository-bound formal public-development slot.
- Kubernetes `k8s-constraint-interactions-dev-005` remains strong development
  evidence: 13 native failure variants, 13 semantic recovery signatures,
  reference recovery 13/13, 117 fixed-policy runs, and ordinary GLM-5.2 1/13.
- The Kubernetes scenario has already been exposed to a model and cannot be
  promoted by changing its split or instance metadata.
- A fresh Kubernetes public-development instance now exists with 13 exact
  native failure boundaries and 13 distinct recovery signatures.
- The formal build-spec adapter freezes reset evidence, boundary bundle, tool
  contract, evaluator and reference bundle before provider access.
- The admitted source run completed 13/13 reference recoveries, all 117 fixed
  policies and replay-derived hard admission.
- Exact reset restores restart the API server, controller-manager, scheduler
  and kubelet, and require controller and node Leases to renew before exposing
  the restored state to a new consumer.

The remaining boundary is deliberate: execution control and ordinary model
evaluation have not yet run against the frozen formal inputs.

## Exact-boundary problem

The Kubernetes family deliberately uses runtime-generated object identities.
For example, the recovery audit must record the exact `metadata.uid` of an
existing migration, transition, or publication Job. Those UIDs are visible to
the model and are checked by the evaluator.

Deleting and recreating semantically equivalent objects generates different
UIDs. Resetting and replaying external events can also change attempt history.
Therefore the current reset procedure produces an equivalent business state,
but not the same failure boundary.

The shared formal protocol is intentionally stricter:

1. the deterministic reference starts from the admitted boundary bytes;
2. every fixed policy starts from that same boundary;
3. the pre-model boundary capture equals the locked boundary bytes;
4. completion evidence remains hash-linked to those inputs.

The existing Kubernetes workflow cannot satisfy these statements by replaying
manifests. Wrapping its reports in formal envelopes would falsely claim exact
replay.

## K0: native snapshot-replay feasibility gate

Before any fresh instance work, implement and execute one isolated snapshot
spike against the pinned `kind` / Kubernetes runtime.

### Snapshot bundle

One bundle must contain:

- a live etcd snapshot taken after a failure boundary is stable;
- the external event registry SQLite database from the same boundary;
- the exact instance specification;
- the pinned Kubernetes, kind, node-image and control-service identities;
- a manifest containing SHA-256 and byte size for every restore artifact;
- one canonical boundary capture containing all decision- and scoring-relevant
  object fields, including Kubernetes UIDs, plus external idempotency records
  and attempt counts.

Raw Kubernetes responses contain timestamps, resource versions, managed fields,
controller events and other volatile data. The canonical capture must use an
explicit, versioned normalization contract. It may omit a volatile field only
when the model neither needs it for a valid decision nor can be scored on it.
UIDs and external idempotency identities may not be normalized away.

The implemented `kubernetes-interaction-boundary-v6` contract separates
persistent recovery authority from controller-runtime projections. Empirical
two-consumer replay showed that rewinding etcd after one consumer has run makes
kubelet recreate workload Pods and makes Deployment/ReplicaSet controllers
re-emit scaling Events. Their names, UIDs, condition order and messages can
therefore differ even though every persistent recovery fact is identical.

The canonical boundary retains all scored ConfigMap, Secret, Service,
Deployment, Job and RBAC identities, authored specifications, Job evidence,
contract facts and external idempotency records. It excludes Pods and
Deployment/ReplicaSet/Pod lifecycle Events, and treats Kubernetes condition
arrays as maps keyed by condition type. Version 6 additionally excludes the
automatically projected `kube-root-ca.crt` ConfigMap: every fresh kind cluster
creates a different root certificate, while that certificate is neither
authored task state nor read by the evaluator or reference recovery. All other
ConfigMaps, object UIDs, contracts and external identities remain exact. These
excluded fields are neither read by the evaluator nor used by the reference
recovery to derive scope. Ordinary live tools may still expose them as
diagnostics; they are not claimed as exact persistent boundary authority.

### Restore proof

The spike must perform the following sequence in one clean native job:

1. construct one real failure boundary;
2. capture and hash the canonical state;
3. snapshot Kubernetes and the external registry;
4. perform destructive mutations in both systems;
5. restore the bundle;
6. wait for the API server and controllers to stabilize;
7. recapture the canonical state and require byte equality with step 2;
8. repeat the mutation/restore/capture cycle a second time;
9. run the deterministic reference from the restored boundary;
10. restore once more and prove the next consumer starts from the same bytes.

The proof must explicitly check:

- every scored Kubernetes object keeps the same UID;
- every external event keeps the same idempotency key, payload and attempt
  count;
- the evaluator sees the same counterfactual facts before and after restore;
- no controller writes a decision-relevant field after the stable capture;
- the restored boundary can still be modified through the public tools.

### Implementation direction

The preferred implementation is an etcd snapshot plus restore, not a YAML
export/import. Kubernetes stores API objects and their UIDs in etcd. The
external registry already uses SQLite and should run with a mounted data path
so its database can be stopped, copied and restored as part of the same bundle.

The restore implementation must follow the pinned etcd version's supported
procedure. Restoring an older Kubernetes revision can invalidate controller
watches, so the spike must either use a revision bump and compaction marker or
prove that rebuilding the short-lived cluster from the restored keyspace avoids
stale informer state. This is an empirical admission test, not an assumption.
After each rewind, the implementation changes a dedicated replay-token
annotation in the API server, controller-manager and scheduler static-Pod
manifests. Rebuilding the API server is required because its watch cache can
otherwise acknowledge writes while serving the pre-restore object projection;
rebuilding the other two consumers clears their informer caches. Directly
stopping the same containers repeatedly is forbidden because kubelet can
interpret it as repeated failure and apply crash-loop backoff.

Container replacement and API readiness alone are insufficient: a restored
controller can be running before its informers and leader election are ready.
The restore gate therefore observes both the controller-manager and scheduler
leader-election Leases renew after the restart before handing the boundary to
the next reference, policy or model consumer.

The node kubelet is a fourth state consumer. A scheduled Pod can otherwise
remain Pending indefinitely after an etcd rewind even when the scheduler and
Job controller are healthy. The restore procedure therefore restarts kubelet
and requires its Node Lease to renew before exposing the restored boundary.

Official operational references:

- <https://etcd.io/docs/v3.7/op-guide/recovery/>
- <https://kubernetes.io/docs/tasks/administer-cluster/configure-upgrade-etcd/>

## Revised implementation order

### K0 — exact native replay

Implement `snapshot-bundle`, `restore-bundle`, canonical state capture and the
two-cycle restore proof. No model provider is called. Failure of any identity
or state-equality check blocks the rest of the slice.

### K1 — fresh instance specification

After K0 passes, extract all application, namespace, object, contract, external
event and audit identities into a frozen instance specification. Preserve the
current `orders` values as the default compatibility fixture. Add a genuinely
new `public-dev` instance with different business identities and data. A
novelty validator must reject relabelled `dev-005` data.

### K2 — native validation on the fresh instance

Construct all 13 variants before provider access. For each reference boundary:

- snapshot the bundle;
- run and replay the reference;
- derive hard admission from executable evidence;
- require the existing task-difficulty gates;
- prove that one fixed action sequence cannot solve the matched group.

The nine fixed policies are admission probes rather than compared model runs.
Each policy therefore constructs its own native instance of the same declared
counterfactual boundary and byte-locks that state immediately before execution.
It does not claim runtime-generated UIDs equal the reference instance. This
keeps fixed-policy admission executable without spending an etcd restore for
all 117 probes. Execution controls and model runs remain bound to the frozen
reference bundles and may not use this semantic-instance exception.

### K3 — formal evidence portability

Add a Kubernetes generator for the domain-neutral formal build specification.
Build the same seven roles used by the ERPNext slot:

- reset evidence;
- boundary bundle;
- tool contract;
- evaluator;
- reference bundle;
- execution control;
- raw run archive.

Freeze the five provider-input roles and their input lock before any model
credential is made available.

Implementation status (2026-08-02): **K3 is CI-admitted** through two linked,
provider-free GitHub Actions runs.

- [Source admission run 30723666432](https://github.com/fengyw23/AftermathBench/actions/runs/30723666432)
  at commit `62ce525cc7ea8172eee89033250c6029489fa8fe` created one exact reset bundle,
  restored and snapshotted all 13 native failure boundaries, recomputed 13/13
  reference recoveries, completed all 117 fixed-policy probes, and passed the
  replay-derived hard admission gate.
- [Formal-input continuation run 30731884466](https://github.com/fengyw23/AftermathBench/actions/runs/30731884466)
  downloaded that run's immutable artifact, reverified source provenance and
  completed admission, canonicalized only the order of the exact runtime file
  inventory while proving that every path, byte count and SHA-256 stayed
  identical, froze all five provider-input roles, generated the formal input
  lock, and passed the public-evidence safety scan.

The split is an engineering continuation, not a relaxed evidence path. The
first run's 13 exact-reference replays and 117 native policies each took about
two hours, exceeding the earlier 240-minute job budget when combined with
formal packaging. The continuation consumes the immutable uploaded evidence
and cannot rewrite the admitted native trajectories.

Supersession note (2026-08-02): the two runs above still prove the exact-replay
and formal-input packaging mechanisms, but they are no longer the active K4
input. A pre-K4 trajectory audit found that the explicit execution-control
target required the failed change's three candidate artifacts to be absent
while a broad preservation sentence simultaneously said to preserve every
pre-existing object identity. The historical GLM-5.2 control's only failure,
`state_02`, followed the preservation sentence and retained the candidate
credential. That is an instruction-contract ambiguity, not a recovery error.

Commit `4f033a9f7f2d479586a747621390fcf69a4d4c5e` therefore made candidate
artifact disposition explicit and limited preservation to the identities and
evidence that the evaluator actually protects. The first replacement source
run, `30733609127`, was rejected before native startup because the new K4
workflow had copied the fresh scenario identifier into infrastructure code;
the novelty gate correctly treated that as an identity leak. Commit
`8a967fcdc5ebd224b367cbb98768e1af00a6b222` now derives all K4 identity fields
from the frozen scenario instead. Its provider-free replacement source run is
[30733738216](https://github.com/fengyw23/AftermathBench/actions/runs/30733738216).
Run `30733738216` succeeded and produced both the public formal-input artifact
and the short-lived exact replay bundles. The first K4 run, `30741680378`, was
nevertheless rejected before any model call: a restored boundary on a newly
created kind cluster differed from the frozen capture. Corrected diagnostics
(`30744116130` and `30744159752`) proved that the snapshot contained all task
records and that five stable recaptures differed at exactly one path, the
fresh cluster's projected `kube-root-ca.crt` certificate. No GLM-5.2 score can
be inferred from that run because it completed zero model trials.

Boundary v6 removes only that non-task runtime projection and adds a K3
admission step that deletes and recreates kind, restores representative
`state_01` and `state_13` bundles, and byte-compares their normalized task state
before formal inputs are frozen. K4 remains blocked until the replacement K3
run succeeds under this stronger cross-cluster portability check.

### K4 — execution control and model evaluation

Run the explicit-scope execution control first. It must achieve at least 80%
and any failure must be an execution failure rather than boundary drift. Only
then run the ordinary-condition model experiment from exact restored bundles.

The K4 workflow is intentionally gate-only. For every variant it restores the
K3 byte-locked boundary, recaptures canonical state, byte-compares that capture
with the locked evidence, verifies the formal input lock, and only then exposes
the step-scoped Bailian credential. It publishes a non-sensitive aggregate
summary containing the 13-case completion count, pass rate, component rates,
failure counts and provider-error count. Model messages and native restore
archives are not part of that summary.

### K5 — deliberate release binding

Audit the uploaded artifact for credentials and unrestricted native restore
state. Import only the safe repository-ready scenario and formal evidence.
Bind the Kubernetes slot only after local runtime, formal-role, release-manifest
and full test validation succeeds.

The K5 import path is also gate-only and provider-free. Its independent Python
validator rejects duplicate JSON keys, a mismatched workflow or commit, an
expired/empty/undigested artifact, non-discrete or sub-threshold 13-case scores,
extra archive roots, symlinks and unsafe public evidence. A successful import
generates `k5-release-binding-candidate.json`; it deliberately does **not** edit
`data/release_manifest.json`. Release-slot promotion therefore remains a
separate reviewed decision rather than a side effect of a green model run.

## Failure branches

If K0 cannot preserve UIDs and external identities, do not weaken the formal
validator and do not relabel reconstructed state as exact replay. Choose one of
the following explicitly:

1. replace the Kubernetes task contract with stable native correlation records
   whose identities are snapshot-replayable, then rebuild and revalidate the
   family; or
2. adopt a different fully open Kubernetes runtime whose datastore supports the
   required deterministic snapshot lifecycle, while preserving ordinary native
   tools and controller behavior.

Either branch invalidates the current public-development candidate and requires
a fresh instance. Historical `dev-005` results remain development evidence.

## Resume condition

The paused goal can resume without changing its objective. Its first active
slice must be K4: explicit-scope execution control against the frozen formal
inputs. Provider-backed ordinary-condition evaluation remains prohibited until
that control achieves the stated threshold and any failures are shown to be
execution failures rather than boundary drift. Hidden-test generation and a
Kubernetes release-slot claim remain K5 work.
