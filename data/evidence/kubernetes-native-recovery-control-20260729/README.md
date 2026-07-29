# Kubernetes native boundary and reference-recovery evidence

This directory archives selected outputs of GitHub Actions run `30431311972`
(`kubernetes-runtime`, conclusion `success`) at commit
`6ccea9518039e41bc5a227c480cf7bb8ddd4cfbb`.

All four matched boundaries passed, and the state-driven reference used only
the same generic tools exposed to a model. Every terminal evaluation passed:

| Variant | Required recovery mutations |
|---|---|
| patch request did not reach API server | patch Deployment, patch ConfigMap, patch Service |
| patch committed and rollout completed | patch ConfigMap, patch Service |
| patch committed while Deployment paused | resume Deployment, patch ConfigMap, patch Service |
| v2 ReplicaSet pending behind native Node taint | remove taint, patch ConfigMap, patch Service |

The reference issued 15 read/wait calls per variant and verified Deployment,
ReplicaSets, Pods, Events, Nodes, EndpointSlices, HPA, PDB and the protected
`billing-worker`.

The fixed policies were subsequently replayed in successful run
[`30434024218`](https://github.com/fengyw23/AftermathBench/actions/runs/30434024218).
The compact boundary tree passed `4/4`, giving a maximum fixed-policy pass
rate and matched-group success of `100%`. The formal fixed-policy hard gate
therefore failed. Together with GLM-5.2's `4/4` result, this classifies the
family as a useful native easy/candidate control rather than a hard task.
`baselines/summary.json` records the deterministic rejection.

The archive contains no kubeconfig, cluster credential or runtime log.
