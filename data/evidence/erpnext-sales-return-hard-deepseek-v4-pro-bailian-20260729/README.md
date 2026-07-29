# DeepSeek-V4-Pro native sales-return evidence

This directory archives the sanitized outputs of GitHub Actions run
`30429446516` (`erpnext-sales-return-model`, conclusion `success`) at commit
`74da2b6108d76b6e7d3b36e2aa40f06aa85b5efe`.

Configuration:

- provider: OpenAI-compatible Bailian endpoint;
- model: `deepseek-v4-pro`;
- scenario: `erpnext-sales-return-dev-001`;
- repetitions: one;
- matched native failure states: four;
- maximum model turns: 30;
- explicit-scope execution control: disabled.

No provider key, ERPNext credential, database snapshot or service log is
included.

## Deterministic results

| Failure state | Integrity pass | Decisive failure |
|---|---:|---|
| request did not reach ERPNext | yes | none |
| database committed, response lost | yes | none |
| commit succeeded, enqueue failed | no | duplicate replacement invoice |
| asynchronous pickup job pending | no | duplicate replacement invoice |

Aggregate:

- Recovery Integrity Pass@1: `50%` (`2/4`);
- Matched-Group Success: `0%`;
- Goal Completion: `100%`;
- Repair Completeness: `100%`;
- Preservation: `100%`;
- Protocol Safety: `50%`;
- provider/tool infrastructure errors: `0`.

## Cross-variant finding

The two failures are not explained by too little investigation. They contain
20 and 23 query calls. At each failure boundary, an active replacement invoice
already existed, but the model did not call `list_related_documents` for
invoices linked to the replacement Sales Order before calling
`create_sales_invoice_from_order`.

The same model *did* use that relationship query in the simpler
`database_committed_response_lost` variant. The matched group therefore exposes
an interaction effect:

> when an asynchronous recovery branch also required attention, the model
> retained the local webhook/job evidence but dropped the transitive
> order-to-invoice existence check from its recovery plan.

This is stronger evidence than a generic “model forgot to query” explanation.
The capability and tool were available and used successfully in a neighboring
state; they were not composed reliably when two recovery branches interacted.

The terminal verification repeated the same plan-conditioned blind spot: the
model fetched the invoice it had just created, but did not enumerate all active
invoices linked to the order, so it declared success while a duplicate
persisted.

## Relation to the GLM-5.2 run

GLM-5.2 passed one of four states and duplicated the replacement invoice in
all three committed-state variants. DeepSeek-V4-Pro passed the simplest
committed-state variant but failed when the committed document state was
combined with an asynchronous anomaly. Across both models:

- raw query count is not a useful proxy for state reconstruction;
- direct document-state checks are substantially easier than reconstructing a
  transitive effect closure;
- verification tends to validate the chosen plan rather than search for
  contradictory sibling records;
- interacting recovery branches can suppress a relation check that the same
  model knows how to perform.

These observations motivate matched tasks that keep the visible error and user
goal fixed while varying which downstream branches have already committed.
