# Kubernetes orchestrated settlement — GLM-5.2

- GitHub Actions run: `30439726861`
- Commit: `1400938`
- Provider: Alibaba Cloud Bailian
- Model: `glm-5.2`
- Execution control: disabled
- Completed runs: 4/4
- Provider/runtime errors: 0

The raw evaluator reported 0/4 because it required
`settlement-audit[2026-07.receipt_sha256]`. That duplicate hash was not required
by the user instruction or visible policy. Every trajectory correctly recorded
the target batch, `recorded` status and actual Job UID, and all other checks
passed. The evaluator was revised without changing any trajectory; the
versioned `rescored-summary.json` reports 4/4 (100%).

Both raw and rescored reports are retained. The invalid 0% result must not be
used as model-performance evidence. The valid finding is that GLM-5.2 saturates
this structurally admitted development task in one repetition.

No API credentials are stored here.
