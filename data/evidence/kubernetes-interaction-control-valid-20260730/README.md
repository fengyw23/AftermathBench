# Valid Kubernetes interaction execution control

This directory preserves all sanitized trajectories and failure boundaries
from GitHub Actions run
[`30522367760`](https://github.com/fengyw23/AftermathBench/actions/runs/30522367760)
at commit `54e48ab0b0686f103dd1b33b780401d6f2d0a64f`.

The model was given the correct semantic recovery direction for each of the
13 matched hidden states. It passed 12/13 states (92.31%), exceeding the
pre-registered 80% execution-control gate. Goal completion passed in 12/13;
repair completeness, preservation, and protocol safety each passed in 13/13.
There were no provider, runtime, tool, external-key, or protocol errors.

The only failure, `state_02`, is a genuine execution-scope miss. The supplied
direction required compensating the accepted preparation and discarding the
failed candidate. The model emitted the compensation and audit events and
repaired all three local ledgers, but did not delete the candidate Deployment
and Secret. The deterministic evaluator therefore failed only
`candidate_artifacts_match_commit`.

`model-runs/summary.json` is the original workflow output;
`model-runs/analysis.json` is the independent trajectory analysis; and
`model-runs/rescore.json` reruns the corrected scalar-normalizing evaluator.
The rescore changed zero outcomes, showing that the replacement run no longer
depends on the invalid hidden scalar-type rule found in the earlier control.

`files.json` contains relative paths, sizes, and SHA-256 hashes for every raw
artifact retained before audit metadata was added. The archive contains no API
key, authorization header, kubeconfig, or credential file.
