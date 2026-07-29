# Kubernetes settlement candidate — GLM-5.2

This directory preserves the first valid model run after aligning the receipt
status check with the model-visible Job output.

- GitHub Actions run: `30436930316`
- Native replay/baseline run: `30436926013`
- Commit: `1b78c9c`
- Provider: Alibaba Cloud Bailian, OpenAI-compatible endpoint
- Model: `glm-5.2`
- Execution-control prompt: disabled
- Repetitions: one
- Completed trajectories: 4/4
- Recovery Integrity Pass: 4/4 (100%)
- Matched-group success: 1/1 (100%)
- Provider/runtime errors: 0

The native replay independently passed all four boundaries and all four
public-tool reference recoveries. Fixed-policy admission nevertheless rejects
the task as hard: `compact_state_tree` passes 4/4 and `assume_committed` passes
3/4. Raw boundary, reference, baseline, and model trajectories are retained
alongside their machine-generated summaries.

The result is valid but does **not** establish a hard task. It shows that this
scenario is a useful executable candidate/easy control: after the model
distinguishes the primary Job state, every variant requires nearly the same
downstream Lease, delivery, receipt, and ledger sequence. A compact state tree
therefore also solves all variants.

An earlier run (`30436275029`) was initially reported as 0/4 because the
evaluator privately required receipt status `complete` even though the Job log
visible to the model emitted `approved`. That evaluator convention was removed;
the earlier raw trajectories rescore to 4/4. This directory uses a fresh run on
the corrected evaluator rather than overwriting the earlier evidence.

No API credentials are stored in this directory.
