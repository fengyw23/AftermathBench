# GLM-5.2 migration ordinary run — invalid for benchmark scoring

- GitHub Actions run: `30445349006`
- Commit: `6bf9d82ef4f813fe30fcf6d0e4b0524a36f5898d`
- Artifact ID: `8721561863`
- Artifact digest: `sha256:9fe994d262a32f5879f0747020c7364787fbc123edcc9d0ccc9bb316877eff57`
- Completed trajectories: 3/4
- Provider timeout: 1/4 (`preparation_escaped_migration_failed`)
- Raw evaluator pass rate among completed trajectories: 0/3
- Valid benchmark score: **not reported**

This run shares the hidden closure-schema and diagnosis defects documented in
the control run. In addition, one provider read timed out and the workflow did
not rebuild the failure boundary and retry. The updated workflow now retries a
provider/runtime failure once from a freshly reconstructed boundary.

These files are diagnostic evidence only. Missing provider output and
model-invisible scored conventions make a task-level or matched-group score
invalid.
