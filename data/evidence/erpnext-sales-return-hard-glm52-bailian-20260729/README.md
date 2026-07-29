# GLM-5.2 hard sales-return development run

This directory preserves the sanitized output of GitHub Actions run
[`30427906077`](https://github.com/fengyw23/AftermathBench/actions/runs/30427906077)
at commit `551e4574a26cff47209454e589e1959b7d6f4e69`.

- provider: Alibaba Cloud Bailian OpenAI-compatible gateway;
- model: `glm-5.2`;
- scenario: `erpnext-sales-return-dev-001`;
- matched variants: 4;
- repetitions: 1;
- infrastructure/tool errors: 0;
- original Recovery Integrity: 1/4;
- matched-group success: 0/1.

All four runs completed the business goal, downstream accounting, preservation,
and external delivery. The three committed-state failures each created a
second replacement Sales Invoice because the model never enumerated Sales
Invoices linked to the replacement Sales Order before calling
`create_sales_invoice_from_order`.

After the run, the evaluator was clarified to distinguish an idempotently
deduplicated external effect from a redundant network attempt. The raw
`async_job_pending` trajectory made two delivery attempts but the receiver
applied one effect. `rescored-summary.json` records the corrected evaluation.
The aggregate remains 1/4 because that run also created a duplicate native
Sales Invoice.
