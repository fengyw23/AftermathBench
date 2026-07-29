# Native recovery benchmark iteration status — 2026-07-29

## Current boundary

The repository has one replay-admitted hard ERPNext family and two additional
open-source native runtimes under active validation:

| Domain | Source/runtime status | Native reset | Failure family | Model evidence |
|---|---|---|---|---|
| ERPNext sales return | source built and hard-admitted | passed | 4/4 replayed; hard gate passed | GLM-5.2 1/4; DeepSeek-V4-Pro 2/4 |
| Forgejo PR release | source built from pinned revision | passed | 15-write prefix passed; four boundaries and reference control running | pending |
| Kubernetes rollout | kind built from source; Kubernetes node digest pinned | passed | four native boundaries running | pending |

No multi-domain benchmark claim is made yet.

## ERPNext model results

Both model experiments used the ordinary public recovery tools and deterministic
terminal-state scoring. Provider and tool infrastructure errors were zero.

| Model | Recovery Integrity | Matched group | Goal | Completeness | Preservation | Safety |
|---|---:|---:|---:|---:|---:|---:|
| GLM-5.2 | 1/4 | 0/1 | 4/4 | 4/4 | 4/4 | 1/4 |
| DeepSeek-V4-Pro | 2/4 | 0/1 | 4/4 | 4/4 | 4/4 | 2/4 |

GLM-5.2 passed only the no-commit variant. DeepSeek-V4-Pro passed the
no-commit variant and the simplest committed-response-lost variant. Every
failure ended with a duplicate active replacement Sales Invoice.

## Findings exposed by full trajectories

### Query volume is not relationship coverage

Failed trajectories issued many reads and correctly inspected the return,
credit note, replacement delivery, quality inspection, shared payment,
background jobs, external receiver, stock ledger and protected documents.
They still omitted the order-to-invoice existence relation before creating an
invoice.

The failure is not simply “the model did not investigate.” It is a
relationship-coverage failure: broad record inspection missed a particular
downstream-generation edge.

### State reconstruction is asymmetric

Both models treated the ambiguous primary record conservatively: they checked
whether the Sales Return submitted before retrying. They did not apply the
same discipline to transitive native effects created by post-submit
automation. This exposes a measurable distinction between:

- direct commit-state reconstruction; and
- transitive effect-closure reconstruction.

### Interacting recovery branches suppress known checks

DeepSeek-V4-Pro used `list_related_documents` to find the already-created
replacement invoice in the simple committed-state variant. The same model
omitted that check in two matched variants where it also had to handle an
enqueue failure or a pending asynchronous job.

The relevant capability and tool were therefore available. The model failed
to compose them when two recovery branches interacted. This “branch
interference” finding is more specific than lack of tool knowledge and can be
tested directly with matched variants.

### Verification follows the chosen plan, not the environment

After creating a duplicate, models fetched the invoice they had just created
and verified that it was paid. They did not re-enumerate all invoices linked
to the order, then declared that the state was consistent. Terminal
verification was plan-conditioned rather than invariant-conditioned.

### Read/write batching can invert safe recovery order

Some trajectories submitted a mutation and queried decisive state in the same
tool-call batch. Because the writes were executed before all evidence was
interpreted, parallelism became a recovery safety error rather than merely an
efficiency choice.

### Exactly-once effect and redundant attempt must be separated

The external receiver uses an idempotency key. Two HTTP attempts may produce
one applied business effect. Recovery Integrity therefore checks the applied
effect count; redundant delivery attempts are reported separately as execution
waste.

## Immediate hypotheses to test

1. **Effect-closure hypothesis:** models check the directly failed object but
   omit downstream records created by native callbacks.
2. **Branch-interference hypothesis:** an additional recovery branch suppresses
   a relation check that the same model performs in isolation.
3. **Plan-conditioned verification hypothesis:** models validate records they
   acted on rather than enumerate invariants over all related records.
4. **Read/write batching hypothesis:** parallel tool use increases unsafe
   mutation when decisive reads and writes share a batch.
5. **Cross-domain transfer hypothesis:** the same failures should recur for
   Forgejo merge → webhook/release effects and Kubernetes Deployment →
   ReplicaSet/Pod/EndpointSlice effects.

Forgejo and Kubernetes test these hypotheses with different native object
models rather than renamed ERP records.
