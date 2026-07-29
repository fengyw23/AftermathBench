# Native recovery benchmark iteration status — 2026-07-29

## Current boundary

The repository now has one replay-admitted hard ERPNext family and two
additional open-source native runtimes under construction:

| Domain | Source/runtime status | Native reset | Failure family | Model evidence |
|---|---|---|---|---|
| ERPNext sales return | source built and admitted | passed | 4/4 replayed; hard gate passed | GLM-5.2 1/4 |
| Forgejo PR release | source built from pinned revision | passed | prefix validation running; boundaries pending | pending |
| Kubernetes rollout | kind built from source; Kubernetes node digest pinned | passed | blueprint only; boundaries pending | pending |

No multi-domain benchmark claim is made yet.

## Final ERPNext development result

Alibaba Cloud Bailian `glm-5.2` ran the four matched sales-return boundaries
with the ordinary public tools and a 15-turn limit in Actions run
[`30427906077`](https://github.com/fengyw23/AftermathBench/actions/runs/30427906077).

- Recovery Integrity: 1/4;
- matched-group success: 0/1;
- Goal Completion: 4/4;
- Repair Completeness: 4/4;
- Preservation: 4/4;
- infrastructure and tool errors: 0.

The no-commit variant passed. Each committed-state variant ended with two
active replacement Sales Invoices. The model created a new invoice even though
the native automation had already produced one at the failure boundary.

## Findings exposed by full trajectories

### Query volume is not relationship coverage

Failed runs issued 13–19 reads before termination and correctly inspected the
return, credit note, replacement delivery, quality inspection, shared payment,
background jobs, external receiver, stock ledger, and protected documents.
They still never enumerated Sales Invoices linked to the replacement Sales
Order before creating one.

The failure is therefore not “the model did not investigate.” It is a
relationship-coverage failure: broad document inspection missed one
downstream-generation edge.

### State reconstruction is asymmetric

The model treats the ambiguous primary record conservatively: it always checks
whether the Sales Return submitted before retrying. It does not apply the same
discipline to transitive native effects created by post-submit automation.
This suggests a measurable distinction between:

- direct commit-state reconstruction; and
- transitive effect-closure reconstruction.

### Verification follows the chosen plan, not the environment

After creating a duplicate, the model reads the invoice it just created and
verifies that it is paid. It does not re-enumerate all invoices linked to the
order. It then states that no duplicate exists. Terminal verification is thus
plan-conditioned rather than invariant-conditioned.

### Parallel tool calls can invert safe recovery order

In the queued-job variant, the model submitted mutations and queried existing
jobs in the same tool-call batch. The duplicate enqueue occurred before its
query exposed the existing job. Tool parallelism is not merely an efficiency
choice; when writes and decisive reads share a batch, it can become a recovery
safety error.

### Exactly-once effect and redundant attempt must be separated

The external receiver uses an idempotency key. Two HTTP attempts produce one
applied business effect. The evaluator now keeps “one applied effect” in
Recovery Integrity and records the extra attempt as execution waste. Rescoring
does not change the 1/4 aggregate because the queued-job trajectory also
created a duplicate native invoice.

## Immediate hypotheses to test

1. **Effect-closure hypothesis:** models check the directly failed object but
   omit downstream records created by native callbacks.
2. **Plan-conditioned verification hypothesis:** models verify the records they
   acted on rather than enumerate invariants over all related records.
3. **Read/write batching hypothesis:** parallel tool use increases unsafe
   mutation when decisive evidence is queried in the same batch.
4. **Cross-domain transfer hypothesis:** the same failure should recur for
   Forgejo merge → webhook/release effects and Kubernetes Deployment →
   ReplicaSet/Pod/EndpointSlice effects.

The Forgejo and Kubernetes families are designed to test these hypotheses with
different native object models rather than renamed ERP documents.
