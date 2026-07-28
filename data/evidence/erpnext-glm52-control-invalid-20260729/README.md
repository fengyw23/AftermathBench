# Invalid execution-control run

This directory preserves the sanitized evidence from GitHub Actions run
[`30397098671`](https://github.com/fengyw23/AftermathBench/actions/runs/30397098671)
at commit `7eb94959f1465ba0f68a87a0bf645f495e67a598`.

The run is retained for auditability but is **excluded from control results**.
Its prompt said both that there must be exactly one replacement invoice and
that the agent should "create and submit exactly one replacement invoice".
In the three committed variants, a Return post-submit workflow had already
created a linked draft invoice. The wording therefore induced the same
duplicate creation that the control was intended to remove.

The replacement control states the gold execution scope operationally:

- search Purchase Invoices linked to the replacement receipt before creating;
- reuse and submit one existing draft when present;
- create only after confirming none exists;
- never create a second active replacement invoice.

The ordinary benchmark prompt, task state, tools, evaluator, and main model
result are unchanged.
