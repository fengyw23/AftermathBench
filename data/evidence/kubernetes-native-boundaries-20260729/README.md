# Kubernetes native rollout-boundary evidence

This directory archives selected outputs of GitHub Actions run `30430730093`
(`kubernetes-runtime`, conclusion `success`) at commit
`6c76b5e39ea7172dbe32c214a2f953acec07b2a6`.

The run built `kind` from pinned source, used the digest-pinned Kubernetes
v1.34.0 node image, validated deterministic reset, and replayed all four
matched failure boundaries against the native API server and controllers.

| Variant | Deployment template | Paused | v2 ReplicaSet | v2 ready | Native node blocker |
|---|---|---:|---:|---:|---:|
| patch request did not reach API server | v1 | no | no | 0 | no |
| patch committed, response lost | v2 | no | yes | 3 | no |
| patch committed while reconciliation paused | v2 | yes | no | 0 | no |
| v2 ReplicaSet created, rollout pending | v2 | no | yes | 0 | yes |

Every variant exposed the same surface result:
`HTTP connection lost before a success response`.

The boundary harness does not fabricate Kubernetes objects. It either
suppresses the patch, executes the ordinary patch and drops its result, uses
the native Deployment pause field, or applies a visible native node taint that
causes scheduler Events and pending Pods.

The selected archive excludes cluster credentials and diagnostic logs. The
reference recovery/evaluator is validated in a later run.
