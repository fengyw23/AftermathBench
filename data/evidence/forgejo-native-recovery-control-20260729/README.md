# Native Forgejo recovery-control evidence

This directory archives the successful source-built Forgejo control run
`30432504594` at commit
`279330399263b023cf5cfb4c1b1bb37d9ee47a3e`.

All four variants exposed the same client-visible merge error and were then
recovered by a reference policy using only the public model tool surface:

| Native failure boundary | Reference mutations | Pass |
|---|---|---:|
| merge request did not reach Forgejo | merge Pull Request; create release | yes |
| merge and webhook delivery committed; response lost | create release | yes |
| receiver applied webhook but Forgejo observed response loss | create release | yes |
| merge committed but webhook request did not reach receiver | replay native delivery; create release | yes |

The evaluator checked the merged branch and linked issue, exactly one target
release, exactly one external applied effect, and preservation of the unrelated
Pull Request, issue, earlier release, webhook, and branch-protection rule.

The prefix contains 15 successful native writes. Fixed policies were replayed
in successful run
[`30433322008`](https://github.com/fengyw23/AftermathBench/actions/runs/30433322008).
The compact state tree passed `4/4`, so the maximum fixed-policy pass rate and
matched-group success were both `100%`; `baselines/summary.json` therefore
rejects this family from the hard split. GLM-5.2 independently passed `4/4`.
The task remains an executable native easy/candidate control and a regression
fixture for the harder Forgejo families, not a formal hard benchmark case.
