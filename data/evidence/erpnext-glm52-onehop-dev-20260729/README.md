# GLM-5.2 one-hop-query development regression

This is a four-state development run, not a hidden-test result.

- workflow run: `30422239986`
- source commit: `c305d0e663547550a63591d431c1be48a3187513`
- model: `glm-5.2`
- execution control: `false`
- provider/runtime errors: `0`
- Recovery Integrity: `1/4`
- matched-group success: `0/1`

The run was launched after adding the transparent
`list_related_documents` tool. That tool exposes one native ERPNext link at a
time and does not recommend a recovery action.

## Main result

The model completed the business goal, accounting closure, and preservation
checks in all four states. It nevertheless failed three states because it
created a second replacement invoice.

The failure is not caused by a missing interface:

1. the existing draft replacement invoice was present in the authoritative
   database;
2. `list_related_documents(Purchase Receipt, ..., Purchase Invoice)` could
   expose it directly through the native child-row link;
3. a generic `list_documents(Purchase Invoice)` query was also available;
4. the model used neither query before calling
   `create_purchase_invoice_from_receipt`;
5. every tool invocation itself succeeded.

The request-not-reached state passed because no replacement invoice existed
before the model submitted the return. In the three committed states, the
post-submit workflow had already created that invoice, so the same creation
policy became unsafe.

This matched contrast isolates a recovery-specific investigation failure:
the model checked the named return, debit note, order, and receipt, but did not
enumerate an unnamed downstream record before creating one. Adding a
discoverable relation tool removed the interface excuse without automatically
solving the task.

## Files

- `summary.json`: deterministic aggregate;
- `analysis.json`: trajectory-level error analysis;
- `repetition-01/*.json`: complete sanitized model/tool trajectories;
- `repetition-01/*-failure.json`: exact injected-boundary reports;
- `prefix.json`: replayed native prefix identifiers and write trace;
- `manifest.txt`: scenario, snapshot, model, and commit identifiers.
