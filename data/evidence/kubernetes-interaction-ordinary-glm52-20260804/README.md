# Kubernetes interaction ordinary GLM-5.2 evaluation

This archive contains one complete 13-state ordinary scope-inference sample for
`k8s-constraint-interactions-dev-005`.

## Provenance

- Primary GitHub Actions run: `30865035666` (11 scored trajectories; `state_01`
  and `state_02` were absent after provider retries).
- Infrastructure-only retry: `30872359883` (only `state_01,state_02`, with SSE
  enabled and a 1200-second provider timeout).
- `coverage-manifest.json` was produced by
  `scripts/assemble_native_model_coverage.py`. The assembler rejects any retry
  trajectory for a variant already scored in the primary run, so this archive
  cannot select a more favorable second sample.
- Every copied trajectory is bound to its source run and source/target SHA-256.

## Result

- Completed trajectories: 13/13
- Provider/runtime errors: 0 after coverage assembly
- Recovery Integrity Pass: 2/13 (15.38%)
- Matched-group success: false
- Goal completion: 8/13 (61.54%)
- Preservation: 12/13 (92.31%)
- Protocol safety: 8/13 (61.54%)
- Repair completeness: 2/13 (15.38%)
- Primary error among failures: 11 scope failures

The corresponding explicit-scope execution control is archived separately and
passes 12/13 states. Ordinary failures therefore must not be attributed solely
to an unusable tool surface. `summary.json` is the generic deterministic
aggregate; `analysis.json` contains Kubernetes-specific evidence and failure
diagnostics.
