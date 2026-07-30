# ERPNext sales-return ordinary-condition evidence

This directory preserves the complete sanitized model input, tool calls, tool
results, failure boundaries, and deterministic evaluations from GitHub Actions
run [`30519698310`](https://github.com/fengyw23/AftermathBench/actions/runs/30519698310)
at commit `9e2760a253c41351313f580de3c511cfac6125b3`.

GLM-5.2 ran once on each of the four matched post-error states with ordinary
tools and no supplied recovery scope. It passed two of four states, for a 50%
Recovery Integrity Pass rate and zero matched-group success. Goal completion,
repair completeness, and preservation were 4/4; protocol safety was 2/4.
There were no provider, runtime, or tool-call errors.

Both failures left exactly one duplicate replacement Sales Invoice:

- In `after_commit_enqueue_failed`, a replacement invoice already existed at
  the failure boundary. The model inspected the replacement Sales Order but
  did not query its linked invoices before creating another.
- In `request_not_reached`, no replacement invoice existed at the boundary.
  The model submitted the replacement Delivery Note, which caused the native
  automation to create the invoice, but did not refresh linked state before
  executing its previously planned invoice-creation call.

The second failure is therefore not merely an over-broad terminal scope. It is
a stale-plan failure caused by an unobserved side effect of the model's own
recovery mutation. `analysis.json` records both the original online
attribution and the refined replay-based subtype.

The paired explicit-scope execution control is archived in
`../erpnext-sales-return-control-20260730`. It used the same scenario, source
commit, model, public tools, and one run per state, and passed 4/4 with zero
tool errors. This supports attributing the ordinary-condition gap to state
investigation and plan invalidation rather than inability to operate the
interface. Four trials are still a development result, not a stable model
ranking.

`paired-comparison.json` machine-checks the scenario, source commit, model,
prefix, variant set, condition labels, control threshold, and error counts.
`experiment.json` binds every retained artifact to its SHA-256 digest. The
archive contains no API key, authorization header, database dump, or runtime
credential file.
