# Kubernetes interaction ordinary-condition composite

This directory preserves the complete ordinary GLM-5.2 experiment for
`k8s-constraint-interactions-dev-005`. The selected 13 trajectories score
1/13 Recovery Integrity (7.69%) and 0 matched-group success, compared with
12/13 (92.31%) under the explicit-scope execution control.

The primary ordinary run
[`30527525012`](https://github.com/fengyw23/AftermathBench/actions/runs/30527525012)
used the exact control commit `54e48ab0b0686f103dd1b33b780401d6f2d0a64f`.
It produced 11 trajectories. `state_01` and `state_02` each exhausted three
600-second non-streaming provider attempts without producing a trajectory;
those empty provider failures are excluded rather than scored as model errors.

Three infrastructure-only retries completed the matrix:

- run `30540796138` used an 1800-second provider timeout and produced the
  missing `state_02` trajectory;
- run `30543847725` preserved the failed non-streaming attempts for
  `state_01` but still produced no trajectory;
- run `30549370454` used OpenAI-compatible SSE streaming and produced the
  missing `state_01` trajectory.

The retries did not modify the scenario, prompt, public tools, failure
boundaries, or evaluator. Fresh kind clusters generate different
`kube-root-ca.crt` certificates, so raw prefix hashes differ. After excluding
that runtime-generated system ConfigMap and its derived aggregate fingerprint,
all control and ordinary prefixes have the identical task-state projection
SHA-256:
`0d874013374de673660bad82e7b8330d5d4c88dd529455a377c4478328a9dfca`.

The final selected result is:

| Metric | Explicit scope | Ordinary |
|---|---:|---:|
| Recovery Integrity | 12/13 | 1/13 |
| Goal Completion | 12/13 | 8/13 |
| Repair Completeness | 13/13 | 1/13 |
| Preservation | 13/13 | 12/13 |
| Protocol Safety | 13/13 | 7/13 |

Every ordinary trajectory queried all six registered evidence groups. The
ordinary model therefore did not fail because decisive state was hidden or
because it skipped broad investigation. Twelve terminal states were classified
as scope failures: the model could not consistently combine controller
ownership, transition state, compatibility, shared credential, external
event, and ledger evidence into the required cross-object recovery.

`selected-runs` contains the 13 scored trajectories and their deterministic
summary, independent analysis, and corrected-evaluator rescore.
`selection.json` records the exact source of each selected trajectory. The four
raw run directories are retained so provider failures and transport changes
remain auditable. `files.json` byte-verifies the archive. No API key,
authorization header, kubeconfig, or credential file is present.
