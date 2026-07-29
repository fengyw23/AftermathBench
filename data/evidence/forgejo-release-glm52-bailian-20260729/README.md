# Forgejo PR-release GLM-5.2 run

This directory preserves the complete, sanitized output of GitHub Actions run
[`30433462819`](https://github.com/fengyw23/AftermathBench/actions/runs/30433462819)
at commit `c8154e9ae`.

The source-built Forgejo runtime and provider completed without infrastructure
errors. GLM-5.2 passed all four matched ambiguous-failure variants:

| Variant | Recovery Integrity |
|---|---:|
| merge request not reached | pass |
| merge committed, delivery succeeded | pass |
| merge committed, receiver accepted but response lost | pass |
| merge committed, delivery request not reached | pass |

Task Pass@1 and matched-group success were both `100%`. The trajectories show
that the model reconstructed the PR, branch, issue, webhook, receiver and
release state and selected the appropriate merge/replay/release operations.
They also show that this first Forgejo family is not a hard task: a compact
state tree over merge state and webhook delivery state is sufficient. It is
therefore retained as a native candidate/easy control, not evidence that the
formal hard split is solved.

`model-runs/repetition-01` contains the full model messages, public tool calls,
tool results, final native evidence and deterministic evaluator output. API and
runtime credentials were removed by the workflow before artifact upload.
