# Invalid Kubernetes interaction control: hidden scalar type

This directory preserves all sanitized trajectories and failure boundaries
from GitHub Actions run
[`30518023055`](https://github.com/fengyw23/AftermathBench/actions/runs/30518023055)
at commit `93af204780d28c120d5a69bffea2634ed0042688`.

The workflow passed its pre-registered 80% control gate with 11/13 states.
Trajectory-level audit found that one of the two reported failures was not a
valid recovery error. In `state_12`, the model supplied JSON number `2` for
`schema_epoch` and `credential_generation`. The public contract declared the
fields but did not declare that their values must be JSON strings. The
evaluator nevertheless compared them to `"2"` using strict Python type
equality.

After normalizing semantically equivalent scalar values, the archived terminal
state passes every check. The corrected score is 12/13. The remaining
`state_01` failure is genuine: despite being given the correct discard scope,
the model left candidate Deployment and Secret objects that the target
required it to remove.

The original score is classified as invalid rather than silently overwritten.
`model-runs/summary.json` is the original output;
`model-runs/rescore.json` records the deterministic correction. A clean
replacement control is running as
[`30522367760`](https://github.com/fengyw23/AftermathBench/actions/runs/30522367760).
No ordinary-condition run will be accepted until that replacement control is
audited.

`files.json` contains relative paths, sizes, and SHA-256 hashes for all 31 raw
files retained before the audit metadata was added. The archive contains no
API key, authorization header, kubeconfig, or credential file.
