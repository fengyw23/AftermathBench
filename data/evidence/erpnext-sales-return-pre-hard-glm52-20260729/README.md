# Pre-hard sales-return GLM-5.2 evidence

This directory preserves the first model run of the native ERPNext customer
sales-return family before fulfillment and billing recovery were separated.
It is a development baseline, not a result for the hard split.

- GitHub Actions run: `30424754256`
- source commit: `beb7252b1d488a02d566d62c4d48708b17518c31`
- provider: Zhipu coding endpoint
- model: `glm-5.2`
- matched states: four
- Recovery Integrity Pass: `2/4`
- Matched-Group Success: `0/1`
- runtime/provider errors: zero

The model completed the business goal in all four states. It failed the two
asynchronous states because it created a second replacement invoice after
the native automation had already created one. The deterministic evaluator
therefore reported `no_duplicate_replacement_invoice = false`. These are
investigation failures: the relevant linked invoice could be queried with
public tools, but the model did not establish whether it already existed
before mutating the system.

The subsequent hard revision separates replacement delivery from replacement
billing. It requires the agent to reconstruct and close both branches instead
of relying on one combined invoice-from-delivery operation. Results from this
directory must not be pooled with that revised task.

`summary.json`, `manifest.txt`, `prefix.json`, the four visible failure
reports, and all four complete sanitized model trajectories are preserved
verbatim from the workflow artifact.
