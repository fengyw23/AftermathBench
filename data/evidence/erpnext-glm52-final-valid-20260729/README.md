# Valid GLM-5.2 easy-versus-frozen-holdout experiment

This directory is the sanitized artifact from GitHub Actions run
[`30407901921`](https://github.com/fengyw23/AftermathBench/actions/runs/30407901921)
at experiment commit `afcf9638b4cc4e3c4f031dda146a8edc6e246c16`.

The same job built pinned ERPNext/Frappe once, ran the easy payment pilot
against four hidden states for five repetitions, rebuilt a clean native
environment, verified the frozen holdout hashes, and then ran the hard partial
return family under the same model, provider, 15-turn budget, and public-tool
condition.

## Primary results

| Metric | Easy pilot | Frozen hard holdout |
|---|---:|---:|
| Completed trajectories | 20/20 | 20/20 |
| Recovery Integrity Pass | 20/20 (100%) | 6/20 (30%) |
| Matched-Group Success | 5/5 (100%) | 0/5 (0%) |
| Goal Completion | 100% | 100% |
| Repair Completeness | n/a | 100% |
| Preservation | 100% | 100% |
| Protocol Safety | 100% | 30% |
| Provider/runtime errors | 0 | 0 |

The absolute Recovery Integrity reduction is 70 percentage points. All
pre-registered acceptance checks in `comparison.json` are true.

Hard-variant pass rates:

- request not reached: 5/5;
- database committed, response lost: 1/5;
- committed, pickup enqueue failed: 0/5;
- pickup job pending: 0/5.

All 14 failed hard trajectories completed the user-visible business goal,
repair completeness, and prefix preservation, but failed protocol safety.
Every one created a duplicate replacement invoice without first listing the
Purchase Invoices already linked to the replacement receipt. One of those
trajectories also failed the exactly-once pickup check. Both the online
diagnostics and the independent post-hoc analysis classify the 14 failures as
investigation failures.

## Integrity audit

- easy trajectories: 20;
- hard trajectories: 20;
- second provider attempts: 0;
- provider/runtime failures: 0;
- model tool-call errors: 0;
- hard trajectories with `execution_control=false`: 20/20;
- hard scenario id: `erpnext-partial-return-holdout-001`;
- model: `glm-5.2`;
- `comparison.json` SHA-256:
  `1bb6cf7f22d14bc505cdc4f0e06cf8e444e63e1b21e181ff6e93ae8919d0046b`.

Frozen holdout identifiers:

```text
scenario SHA-256:
8f09a09aa477a92d996aa10474c88c7122ea99376b2d330888bc4fb2b335c60d

prefix SHA-256:
88b701ed570406de4395247ec4982cde0df9131a853ad38e7489ff54e4c03f3e
```

`holdout/runs/analysis.json` is derived from the raw trajectories by
`scripts/analyze_native_model_runs.py`. No credentials, authorization headers,
database dumps, API keys, or hidden chain-of-thought are included.
