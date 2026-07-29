# Kubernetes native runtime

This runtime uses a source-built `kind` v0.30.0 control binary and the exact
digest-pinned Kubernetes v1.34.0 node image published for that kind release.
The API server, controllers, scheduler, kubelet, etcd state, Events,
ReplicaSets, Pods, Services, EndpointSlices, Jobs, and Leases are therefore
native Kubernetes components rather than benchmark reimplementations.

The first task family is a Deployment rollout whose patch call reports the
same connection loss at four different transition boundaries. Recovery must
be based on ordinary Kubernetes reads and writes. The benchmark must never
expose a global state summary or a `repair_rollout` tool.

This directory is currently a source-audited scaffold. It is not execution
admitted until cluster reset, all fault variants, reference recovery, terminal
checks, and hard admission have been replayed in CI.
