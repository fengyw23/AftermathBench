# Kubernetes schema-rollout recovery — native validation

- GitHub Actions run: `30446998595`
- Commit: `71be17a6f4747ac202cdb4dd966d59cfc57b0afa`
- Artifact: `kubernetes-migration-30446998595`
- Artifact digest: `sha256:a9d2eb3cf2a4fe1317dfbfc84bdc13cc34c313e0143f90160e765d9cfbf086ea`
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

This run supersedes the earlier native artifact from `30443406478`. It includes
the model-visible audit/event contracts and unambiguous release-ledger
semantics added after the first invalid model audit.

Model evidence is intentionally not included here. It is archived separately
after the execution-control and ordinary model conditions finish.
