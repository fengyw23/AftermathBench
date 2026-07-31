# Kubernetes formal-continuation gate -- 2026-08-01

## Purpose

This checkpoint decides whether the paused long-running goal can safely resume
with the Kubernetes formal public-development slice. It audits the current
runtime against the repository's exact-boundary evidence contract and replaces
the previous immediate plan with a gated implementation order.

The high-level goal remains correct. The next implementation step must change.
It is not yet valid to parameterize `dev-005`, run another model experiment, or
bind a Kubernetes release slot.

## Current verified position

- ERPNext has the first repository-bound formal public-development slot.
- Kubernetes `k8s-constraint-interactions-dev-005` remains strong development
  evidence: 13 native failure variants, 13 semantic recovery signatures,
  reference recovery 13/13, 117 fixed-policy runs, and ordinary GLM-5.2 1/13.
- The Kubernetes scenario has already been exposed to a model and cannot be
  promoted by changing its split or instance metadata.
- There is no fresh Kubernetes public-development instance, Kubernetes formal
  build-spec adapter, or seven-role formal evidence package.
- The current workflow reconstructs each boundary by deleting and recreating
  the namespace and resetting/reseeding the external event registry.

The last item is a correctness blocker, not merely missing packaging.

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

Construct all 13 variants before provider access. For each exact boundary:

- snapshot the bundle;
- run and replay the reference;
- run all nine fixed policies;
- derive hard admission from executable evidence;
- require the existing task-difficulty gates;
- prove that one fixed action sequence cannot solve the matched group.

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

### K4 — execution control and model evaluation

Run the explicit-scope execution control first. It must achieve at least 80%
and any failure must be an execution failure rather than boundary drift. Only
then run the ordinary-condition model experiment from exact restored bundles.

### K5 — deliberate release binding

Audit the uploaded artifact for credentials and unrestricted native restore
state. Import only the safe repository-ready scenario and formal evidence.
Bind the Kubernetes slot only after local runtime, formal-role, release-manifest
and full test validation succeeds.

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
slice must be K0 only. The automatic loop may proceed to K1–K5 only after the
snapshot-replay proof is green and committed. It must not spend provider calls,
generate hidden tests, or make a second release-slot claim before that gate.
