# Valid DeepSeek-V4-Pro easy-versus-frozen-holdout experiment

This directory is the sanitized artifact from GitHub Actions run
[`30415045805`](https://github.com/fengyw23/AftermathBench/actions/runs/30415045805)
at experiment commit `9fec836d093b254a01d6eb4fd276432dd0dea932`.
The provider profile was Paratera and the exact model identifier was
`DeepSeek-V4-Pro`.

The job built pinned ERPNext/Frappe once, ran the four easy hidden states for
five repetitions, rebuilt a clean native environment, verified the frozen
holdout hashes, and then ran the four hard hidden states for five repetitions.
Both splits used the same public-tool condition and 15-turn budget.

## Primary results

| Metric | Easy pilot | Frozen hard holdout |
|---|---:|---:|
| Completed trajectories | 20/20 | 20/20 |
| Recovery Integrity Pass | 20/20 (100%) | 5/20 (25%) |
| Matched-Group Success | 5/5 (100%) | 0/5 (0%) |
| Goal Completion | 100% | 100% |
| Repair Completeness | n/a | 100% |
| Preservation | 100% | 100% |
| Protocol Safety | 100% | 25% |
| Provider/runtime errors | 0 | 0 |

Hard-variant pass rates:

- request not reached: 5/5;
- database committed, response lost: 0/5;
- committed, pickup enqueue failed: 0/5;
- pickup job pending: 0/5.

All 15 hard failures reached the remaining business goal and passed repair
completeness and valid-prefix preservation, but retained two replacement
invoices instead of one. Thirteen trajectories created a new invoice without
first querying the existing invoices linked to the replacement receipt. Two
trajectories attempted a direct linked-invoice filter using a field that
ERPNext rejected, then continued with invoice creation instead of recovering
with a broader supported query. One of those trajectories also violated the
exactly-once pickup check.

DeepSeek-V4-Pro averaged 10.4 model turns, 20.15 query calls, and 4.85 mutation
calls on the hard split. For comparison, GLM-5.2 averaged 7.15 turns and 13.05
queries, yet showed the same dominant duplicate-invoice failure. The additional
investigation volume therefore did not translate into complete reconstruction
of post-commit downstream effects.

## Integrity audit

- easy trajectories: 20;
- hard trajectories: 20;
- provider/runtime failures: 0;
- model-visible tool-call errors: 4;
- hard trajectories with `execution_control=false`: 20/20;
- hard scenario id: `erpnext-partial-return-holdout-001`;
- model: `DeepSeek-V4-Pro`;
- provider profile: `paratera`;
- experiment acceptance checks: all true.
- `comparison.json` SHA-256:
  `c00d52cda6a5a93c490e75b3ee7ca8b26f5056cf92ea82cf29990ade4de5e607`.

Frozen holdout identifiers:

```text
scenario SHA-256:
8f09a09aa477a92d996aa10474c88c7122ea99376b2d330888bc4fb2b335c60d

prefix SHA-256:
88b701ed570406de4395247ec4982cde0df9131a853ad38e7489ff54e4c03f3e
```

`holdout/run-analysis.json` is derived from the raw trajectories by
`scripts/analyze_native_model_runs.py`. No credentials, authorization headers,
database dumps, API keys, or hidden chain-of-thought are included.
