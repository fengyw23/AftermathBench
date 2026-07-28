# Fully open runtime selection

## Why the runtime policy changed

AftermathBench must distinguish a real recovery failure from behavior invented
by benchmark glue. A dataset, API catalogue, or runnable image is not enough.
For a runtime to support the final benchmark, reviewers must be able to inspect
the server implementation, schema, transaction boundaries, asynchronous
effects, reset procedure, and evaluator evidence.

The current EnterpriseOps ITSM task remains useful as a concept prototype, but
it cannot establish native tool semantics. The public EnterpriseOps-Gym
repository provides tasks, seed databases, client/orchestrator code, and
references to domain MCP images. It does not provide the domain server source
and native transaction implementation. Therefore it is rejected by the formal
runtime gate.

## Selection result

| Substrate | Server, schema, and transaction source | Build and reset under our control | Rich persistent relationships | Decision |
|---|:---:|:---:|:---:|---|
| EnterpriseOps-Gym | No | Partial | Yes | Keep only as a legacy concept prototype |
| AppWorld | Partial | Partial | Yes | Do not use for the strict-open core; important implementation/evaluation bundles have access and redistribution restrictions |
| τ³-bench / tau2 | Yes | Yes | Moderate | Eligible for quick conversational-state controls, not the primary complex enterprise runtime |
| ERPNext + Frappe | Yes | Yes | Yes | Primary enterprise runtime |
| Forgejo | Yes | Yes | Yes | Primary coding/DevOps runtime candidate |
| SWE-bench | Yes | Yes | Code-centric | Use as a task/patch source, not as the persistent recovery runtime by itself |

## Source-level evidence

The following revisions are frozen for the first implementation pass.

### ERPNext and Frappe

- Frappe Docker build definitions:
  `412de117d95b4a7f939993b70838c9d9463fa0cf`, MIT.
- ERPNext: `b9c9b76f5b043bd542b01dd4fefe913416a7bb53`,
  branch `version-15`, GPL-3.0.
- Frappe: `c1afa13e12834dcdc1d82c4ba8bb3e5652163656`,
  branch `version-15`, MIT.
- ERPNext contains 566 DocType JSON definitions and 2,434 Python files in the
  audited checkout.
- Frappe contains 305 DocType JSON definitions and 1,406 Python files.
- `PaymentEntry.on_submit` creates GL entries and updates outstanding amounts.
- `PurchaseReceipt.on_submit` updates the preceding document, stock ledger, and
  GL entries.
- `PurchaseInvoice.on_submit` updates billing state and creates accounting
  entries, with stock effects when applicable.
- `Database.commit` commits SQL before running `after_commit` callbacks.
- Frappe webhooks register queue flushing through `after_commit`.

This gives a source-supported failure boundary: the payment database
transaction may be durable while a post-commit webhook enqueue fails. It does
not justify row-level partial commit inside the payment transaction.

The local lock file uses the official production Containerfile and builds
Frappe `v15.116.0` plus ERPNext `v15.118.1` from source. No prebuilt ERPNext
application image satisfies the execution gate.

### Forgejo

- Audited revision:
  `fbafae6c6288f3448aa6932576841f5daf5a9c76`, MIT.
- The checkout contains 808 model-layer Go files, 130 model-registration
  calls, and 213 API files.
- Public transaction boundaries cover package files, releases and attachments,
  Actions runs, and post-receive processing.

Forgejo is therefore a credible second native domain for recovery after
ambiguous package publication, release creation, Git push hooks, or CI
transitions.

### τ³-bench / tau2

- Audited revision:
  `1d244f5dca42944b67a379b44bfeb9f5748f189d`, MIT.
- The public runtime exposes typed read/write tools, state replacement,
  database hashing, evaluation, and replay in airline, retail, telecom, and
  banking-knowledge domains.

It is useful for a low-cost control suite, but its state graphs are not a
replacement for ERP and DevOps transaction systems.

## Machine-enforced gate

Every runtime manifest records two different statuses:

1. **Source audit:** the implementation, schema, transaction behavior, build,
   redistributable inputs, and authentic fault seam are inspectable.
2. **Execution admission:** the pinned source was built; reset was verified;
   every fault variant was replayed; and terminal checks were replayed.

Passing the source audit does not imply that a runtime is ready for benchmark
experiments. Run:

```bash
python -m aftermath_bench validate-runtimes
```

ERPNext passes both the source and execution gates. The native workflow
successfully built the pinned source, restored a deterministic snapshot,
replayed all four fault variants, and ran their terminal checks in
[`30373948156`](https://github.com/fengyw23/AftermathBench/actions/runs/30373948156).
EnterpriseOps is explicitly rejected at the source gate.

## First native task

The first task is a procurement-to-payment chain:

```text
Purchase Order
  -> Purchase Receipt -> Stock Ledger + receipt GL
  -> Purchase Invoice -> supplier payable
  -> Payment Entry -> payment GL + invoice outstanding
  -> after-commit queue -> remittance webhook
```

Seven successful writes create real commitments before `submit Payment Entry`
returns an ambiguous connection error. All variants show the same surface
failure while authoritative state differs:

1. request never reached Frappe;
2. core transaction committed and only the response was lost;
3. core transaction committed but post-commit enqueue failed;
4. core transaction committed and the job is queued but its worker is paused.

The agent must inspect document, ledger, outstanding-balance, queue, and
delivery state. It must preserve the valid order, receipt, stock, invoice, and
accounting history while completing payment and remittance exactly once.
