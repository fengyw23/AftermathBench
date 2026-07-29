# GLM-5.2 migration control run — invalid for benchmark scoring

- GitHub Actions run: `30445306355`
- Commit: `6bf9d82ef4f813fe30fcf6d0e4b0524a36f5898d`
- Artifact ID: `8721508088`
- Artifact digest: `sha256:835f0ad8c6b83c366c6e3e42adee04e6f56234ec8400d83ddf0f04859b993991`
- Provider/runtime errors: 0
- Completed trajectories: 4/4
- Raw evaluator pass rate: 0/4
- Valid benchmark score: **not reported**

The run exposed two benchmark defects. First, the evaluator required exact
recovery-audit and external-event payload fields that were not present in any
model-visible contract. Second, trajectory diagnosis counted controller state
as investigated only when the model used `list_objects`; all four trajectories
used targeted `get_object` calls and were therefore mislabeled as
`investigation_failure`.

The trajectories are retained because they motivated the evidence-contract and
diagnostic fixes. They must not be used as evidence that GLM-5.2 fails the
recovery task.
