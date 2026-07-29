# GLM-5.2 native Kubernetes rollout evidence

This directory archives the sanitized outputs of GitHub Actions run
`30432127435` (`kubernetes-native-model`, conclusion `success`) at commit
`e5fe193c51821b1005d69d6ca3d429fb9ff0215f`.

Configuration:

- provider: OpenAI-compatible Bailian endpoint;
- model: `glm-5.2`;
- scenario: `k8s-deployment-rollout-dev-001`;
- repetitions: one;
- matched native failure states: four;
- maximum model turns: 30;
- explicit-scope execution control: disabled.

No provider key, kubeconfig, cluster snapshot or service credential is
included.

## Deterministic results

| Failure state | Integrity pass | Model mutations |
|---|---:|---|
| patch request did not reach the API server | yes | apply v2, update ConfigMap, switch Service |
| Deployment committed and reconciled; response lost | yes | update ConfigMap, switch Service |
| Deployment spec committed while paused | yes | resume, update ConfigMap, switch Service |
| v2 ReplicaSet pending behind a visible Node taint | yes | remove taint, update ConfigMap, switch Service |

Aggregate:

- Recovery Integrity Pass@1: `100%` (`4/4`);
- Matched-Group Success: `100%`;
- Goal Completion, Preservation and Protocol Safety: all `100%`;
- provider/tool infrastructure errors: `0`.

## Interpretation

This is valid model evidence but **not evidence that the family is hard**.
GLM-5.2 reconstructed every native boundary and respected the readiness-before-
traffic invariant.  The four outcomes can nevertheless be covered by a short
fixed decision tree over three immediately visible facts: target revision,
Deployment pause state, and the dedicated Node taint.

The result narrows the next construction requirement.  A hard Kubernetes task
must require a larger transitive effect closure in which:

1. no single workload/Node query reveals the recovery branch;
2. two or more controllers can independently have committed downstream state;
3. preserving a shared object rules out an otherwise plausible rollback;
4. a compact fixed tree cannot solve the matched group.

The repository therefore retains this family as a calibrated candidate/easy
case and runs replayed fixed policies before any hard-admission claim.
