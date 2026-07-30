# Forgejo publication execution control

GitHub Actions run
[`30558571437`](https://github.com/fengyw23/AftermathBench/actions/runs/30558571437)
executed `glm-5.2` on all eight matched publication boundaries at commit
`0d4840df92a887c125f0a4288e90b564b9aabc85`.

This is an execution-only control. The model was told the correct
state-dependent recovery rule, but still had to inspect the live Forgejo
repository, attachment set, native webhook histories and external receiver
ledger, then invoke the public tools.

Results:

- Recovery Integrity: 8/8;
- matched-group success: 1/1;
- Goal Completion, Repair Completeness, Preservation and Protocol Safety:
  8/8 each;
- provider/runtime errors: 0;
- scientific execution-control gate: 100% observed versus 80% required.

`model-runs/repetition-01/` retains the complete model-visible input, tool
calls, tool results, final native state and deterministic evaluation for every
variant. No API credential is present.

This result shows that failure in the ordinary condition cannot be attributed
to an unusable tool surface or an unreachable terminal state. It does not
measure whether the model can infer the recovery scope without that guidance.
