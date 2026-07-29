# Kubernetes orchestrated settlement — native validation

- GitHub Actions run: `30438924707`
- Commit: `a876c8f`
- Scenario: `k8s-settlement-orchestrated-dev-002`
- Four fault boundaries: 4/4 valid with one common surface error
- Public-tool reference recovery: 4/4
- Minimum reference mutations: 5
- Distinct mutation signatures: 4
- Distinct partial downstream states: 4
- Maximum fixed-policy pass rate: 25%
- Fixed-policy matched-group solvers: none
- Provider/runtime errors: 0

The four states independently vary the generated Job, Lease, pending receipt,
settlement delivery and audit delivery. The final closure additionally requires
the ledger, audit ConfigMap and CronJob completion marker while preserving the
June settlement and protected schedules.

The raw boundary, reference and baseline reports are retained. Model evidence
is intentionally absent at this stage because the model workflow was held until
native validity and hard admission were established.
