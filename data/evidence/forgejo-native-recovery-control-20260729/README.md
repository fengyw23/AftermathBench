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

The prefix contains 15 successful native writes.  These artifacts establish
that the runtime and four recovery boundaries are executable.  They do not by
themselves establish hard-task admission; replayed fixed-policy results remain
required for that claim.
