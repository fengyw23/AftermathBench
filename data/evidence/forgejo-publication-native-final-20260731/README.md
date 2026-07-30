# Forgejo publication native replay

GitHub Actions run
[`30558008600`](https://github.com/fengyw23/AftermathBench/actions/runs/30558008600)
rebuilt pinned Forgejo from source and replayed the complete
`forgejo-release-publication-dev-002` family.

The artifact records:

- 21 successful native writes before the ambiguous publication error;
- eight matched hidden boundary states with the same visible failure;
- reference recovery success on all eight states;
- 30/30 replayed semantic relations across 19 relation types;
- dependency depth 6 and five distinct correct recovery signatures;
- six fixed heuristics, of which the strongest solved 2/8 states and none
  solved the matched group;
- strict replay-derived admission at the `hard` tier.

The `runtime/` directory contains the frozen prefix, each injected boundary,
reference recoveries, and policy runs. `scenario/` contains the publication
scenario assembled from those observations. `source-verification.json`
identifies the pinned Forgejo source build. The run removed credentials before
uploading this artifact.

This is development-family evidence. It establishes that the task is native,
replayable and mechanically solvable; it is not an independent hidden-test
result.
