# Forgejo publication candidate execution control

This archive records the public, non-sensitive output of GitHub Actions run
[`30568303895`](https://github.com/fengyw23/AftermathBench/actions/runs/30568303895).
The private instance, native snapshots, reference traces, fixed-policy traces
and model trajectories remained on the ephemeral runner and were deleted.

## Result

- The independent instance passed identity-overlap screening.
- The pinned native Forgejo runtime and prefix built successfully.
- All eight matched failure boundaries passed reference recovery.
- The scenario passed replay-derived hard admission.
- Six fixed policies were evaluated across all eight boundaries. The best
  per-case pass rate was `0.25`, and no fixed policy solved the matched group.
- GLM-5.2 execution control passed `8/8` with no provider/runtime errors.
- The immutable bundle bound 167 files and was frozen and reverified before
  the first provider request.
- The usage ledger records `frozen -> evaluation_locked -> consumed`.

The execution control explicitly provides the intended recovery scope. Its
`8/8` result validates that the tool surface and evaluator permit correct
execution; it is not an ordinary-condition model score and does not establish
task difficulty.

This candidate is consumed and must never be described as an unseen
leaderboard test. A preceding run, `30568005984`, stopped during public unit
tests because of a cross-platform evidence-manifest line-ending mismatch. It
did not build or freeze the private state and made no provider request.
