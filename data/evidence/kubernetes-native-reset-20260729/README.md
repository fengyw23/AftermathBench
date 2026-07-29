# Kubernetes native runtime reset evidence

GitHub Actions run
[`30428735478`](https://github.com/fengyw23/AftermathBench/actions/runs/30428735478)
verified the pinned kind and Kubernetes source paths, built the kind control
binary from revision `9a205e8c8540557602240f8766d3c95c51c23c4c`, booted the
digest-pinned Kubernetes v1.34.0 node image, and replayed the rollout prefix.

The semantic prefix fingerprint was:

`bbbe6be81ee60afc736302a7ec97fa8b7731c39dd2e3c06de441c94a49518ba5`

After native Deployment, Service, and ConfigMap mutations it changed to:

`8fe9b81a4b2cdbb3c6548b9254d6a8f5c63792551477e2c0d0415f71ed5a8d68`

Deleting the namespace and rebuilding all objects through the same public API
restored the first fingerprint exactly. Kubernetes-generated identifiers such
as Service `clusterIP`, UIDs, resource versions, and timestamps are excluded
from the semantic fingerprint; selectors, rollout strategy, templates,
autoscaling, disruption policy, and fixture data remain included.

This establishes deterministic original-system reset. It does not yet validate
the four ambiguous patch boundaries or admit the task family.
