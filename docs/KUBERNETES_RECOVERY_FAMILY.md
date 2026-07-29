# Kubernetes Deployment recovery family

## Research purpose

The first Kubernetes family tests recovery after a native Deployment patch
reports a connection loss. The agent must reconstruct both the persisted
desired state and the asynchronous controller state. Reading only the
Deployment is insufficient: a committed template can have no new ReplicaSet,
a progressing ReplicaSet, or a fully ready ReplicaSet, while the Service may
still protect production traffic by selecting v1.

The task therefore spans independently observable native relationships:

1. Deployment generation and controller observation;
2. Deployment ownership of old and new ReplicaSets;
3. ReplicaSet ownership and readiness of Pods;
4. Service selectors and EndpointSlice targets;
5. autoscaling and disruption constraints;
6. a protected unrelated Deployment.

## Matched hidden states

All variants expose the same instruction and the same connection-loss result.

| Hidden state | Necessary investigation | Recovery signature |
|---|---|---|
| Patch did not reach the API server | Deployment template and ReplicaSet revisions still show v1 | apply the v2 patch, observe rollout, then switch traffic |
| Patch committed and rollout completed | Deployment, v2 ReplicaSet and Pods are ready; Service still selects v1 | preserve the rollout and switch traffic only |
| Patch committed but reconciliation is paused | template is v2, generation is not converged, no v2 ReplicaSet exists | resume reconciliation, observe readiness, then switch traffic |
| v2 ReplicaSet exists but rollout is pending | owner references prove the new branch exists, but readiness and Events show it is incomplete | preserve both revisions, complete or wait for the rollout, then switch traffic |

A blind retry can create an unnecessary new Deployment generation. Assuming
success can leave v1 serving forever. Switching the Service before the new
EndpointSlice is ready violates availability. Rolling back everything destroys
a valid v2 rollout in committed variants. These are executable recovery-scope
errors rather than malformed-tool traps.

## Original-system boundary

The API server patch handler, etcd transaction, Deployment controller,
ReplicaSets, Pods, Service, EndpointSlices, HPA, PDB, Events, and owner
references all come from Kubernetes v1.34.0. `kind` is built from its pinned
source revision and the Kubernetes node image is digest pinned. Benchmark code
may drop a request or response and may pause at a native controller boundary;
it may not invent a partially written Kubernetes object or replace controller
logic.

The family remains `unvalidated` until deterministic reset, all four boundary
replays, a state-driven reference recovery, fixed baselines, preservation
checks, and replay-derived hard admission pass in CI.
