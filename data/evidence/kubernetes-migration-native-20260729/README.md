# Kubernetes schema-rollout recovery — native validation

- GitHub Actions run: `30443406478`
- Commit: `cf2e649312b76f0d70ea6f8997d5a34b7d42293a`
- Artifact: `kubernetes-migration-30443406478`
- Artifact digest: `sha256:34a8255951ffc624ebfd5dc929ff7d21cb89f3c06731bac59a5ee964fa34dd7b`
- Scenario: `k8s-schema-rollout-dev-003`
- Reference recovery: 4/4
- Common surface error: yes
- Stable semantic prefix hash: yes (1 hash across 4 boundaries)
- Distinct semantic recovery directions: 4
- Minimum reference mutations: 4
- Maximum fixed-policy pass rate: 25%
- Fixed-policy matched-group solvers: none
- Native hard admission: passed
- Provider/runtime errors: 0

The four boundaries require rollback, external compensation, forward
completion, and downstream-only repair respectively. `runtime/` contains the
raw failure-boundary and reference reports. `baseline-summary.json` records the
executed fixed-policy matrix. The admitted scenario and replay-derived graph
are retained under `data/scenarios/k8s-schema-rollout-dev-003/`.

Model evidence is intentionally not included here. It is archived separately
after the execution-control and ordinary model conditions finish.
