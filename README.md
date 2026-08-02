# AftermathBench

> Current status: the canonical manifest verifies the first formal
> public-development slot: four ERPNext matched cases with native runtime
> admission, strict hard admission, 4/4 execution control and seven-role
> evidence closure. Two additional hard development candidates contain 21
> matched cases. The target matrix still has 35 open slots and no hidden-test
> release, so the repository derives `partial_release`, not a complete
> benchmark. See
> [Top-conference benchmark execution](docs/TOP_CONFERENCE_EXECUTION.md) and
> the current [progress-first execution focus](docs/EXECUTION_FOCUS_20260802.md).

**AftermathBench** evaluates whether a tool-using agent can recover a complex,
persistent environment after a tool call returns an ambiguous failure.

The benchmark begins after a real successful prefix has already created durable
side effects. The same visible error can correspond to no commit, a committed
operation with a lost response, a partial commit, or a queued asynchronous
commit. The agent must inspect authoritative state, repair every affected
dependency, preserve valid prefix effects, and avoid duplicate or unsafe
actions.

## What is measured

```text
Recovery Integrity
= Remaining Goal Completion
AND State and Business Integrity
AND Repair Completeness
AND Valid-Prefix Preservation
AND Protocol Safety
```

AftermathBench does **not** require one gold action sequence and does not score
economic optimality. Any tool trajectory is accepted when its terminal state
and event history satisfy deterministic checks.

## Repository status

The repository contains three legacy concept workflows:

- an enterprise employee transfer;
- a multi-table ITSM major-incident escalation;
- a software release and database migration.

EnterpriseOps-Gym does not publish the domain service implementation and
native transaction logic used inside its MCP images. AftermathBench therefore
labels the ITSM implementation as a **legacy concept prototype**, not a formal
native-runtime task. The release task remains useful as a local design probe,
but is not part of the current primary result.

The formal implementation begins with source-built, version-pinned
ERPNext/Frappe. It provides a digest-pinned service topology, native public-API
writes, real HTTP and queue fault boundaries, full database/queue reset,
ordinary domain tools, and deterministic terminal evaluation. Source-built
Forgejo and Kubernetes/kind runtimes are also executable development
substrates; they are admitted independently rather than counted merely because
their services run.

The current ERPNext scenarios have three distinct statuses:

- `erpnext-procurement-payment-001` is the frozen easy pilot;
- `erpnext-partial-return-{dev,holdout}-001` is the historical challenge used
  for the published cross-model experiment. Under the current stricter gate it
  is a `candidate`, because its shortest valid recovery has three rather than
  four mutations;
- `erpnext-sales-return-dev-001` is a structurally hard-admitted development
  family for
  partial customer return, replacement fulfillment, credit-note
  reconciliation, a shared customer payment, stock/accounting consistency,
  and exactly-once pickup delivery. It is not selected by the canonical
  release manifest. The older raw boundary and recovery files are now
  preserved as historical evidence, but they lack per-variant reset snapshots
  and the current cross-bound formal envelopes; only a fresh native replay can
  satisfy the stricter runtime gate.
- `erpnext-sales-return-public-dev-001-r1` is the fresh, independently
  parameterized public-development instance. GitHub Actions run
  [`30647285786`](https://github.com/fengyw23/AftermathBench/actions/runs/30647285786)
  rebuilt ERPNext/Frappe, captured and replayed all four boundaries, ran all
  fixed policies, passed strict hard admission, froze model inputs before
  provider access, passed the GLM-5.2 supplied-scope control 4/4, and sealed
  all seven formal roles. Its public artifact is now imported and bound as the
  repository's first formal release slot.

The historical partial-return challenge has four matched hidden transition
states behind the same
connection-loss observation. Its complexity is derived from replay artifacts,
its reference recovery passes all variants, seven fixed heuristics have zero
matched-group success, and the holdout scenario and prefix were frozen before
any model access.

The selected Kubernetes constraint-interaction development family passes
replayed hard admission across 13 matched states and 13 named recovery
directions. Its reference recovery passes 13/13, the strongest fixed policy
passes 6/13 without solving the matched group, and the zero-leak prompt audit
covers the complete ordinary input. At the revalidated exact-target revision,
GLM-5.2 passes the supplied-scope control 12/13 but ordinary recovery only
1/13, with zero matched-group success. It remains development evidence, not a
formal benchmark release.

The first Forgejo PR/merge/release family has a real source-built runtime,
native reset, fault boundaries and terminal checks, but a compact state tree
solves its matched group. It is therefore retained as an easy pilot. The
second Forgejo package-publication family contains eight matched boundaries,
two independently faultable downstream consumers, three manifest-bound
attachments, a release milestone and protected unrelated work. Its reference
recovery passes 8/8, all 30 semantic relations replay, and the strongest fixed
policy passes only 2/8 with zero matched-group success. It is hard-admitted as
a development family, not a formal release instance. Its paired GLM-5.2
experiment uses the same source commit and public tools: the explicit-scope
control passes 8/8, while ordinary recovery passes 7/8 and fails the matched
group after replaying two already-successful webhook deliveries. Complete
native, control and ordinary evidence is under
`data/evidence/forgejo-publication-*-final-20260731`.
The 7/8 result is now labeled a pre-contract diagnostic because replay UUID
and stored-payload semantics were not explicit in the original tool
description. The current implementation publishes those stable semantics,
supports parameterized independent instances, snapshots both Forgejo and
receiver state, and freezes a salted evaluator-bundle commitment before any
provider call. An independently named private candidate validated the full
protocol in run
[`30568303895`](https://github.com/fengyw23/AftermathBench/actions/runs/30568303895):
reference `8/8`, best fixed policy `2/8` with no matched-group solver, and
GLM-5.2 supplied-scope execution control `8/8` with no run errors. That
candidate is consumed and is not an ordinary-condition or leaderboard
result. Its public aggregate is archived under
`data/evidence/forgejo-publication-candidate-control-20260731`. See
`docs/FORGEJO_PUBLICATION_INSTANCE_AND_FREEZE.md`.

AftermathBench does not yet claim a complete multi-domain benchmark release.
`data/release_manifest.json` is the authoritative release checkpoint. It
binds each selected scenario, every admission artifact, and its supplied-scope
execution-control summary by SHA-256. `validate-release` verifies these inputs
again instead of trusting a status label. The current manifest is valid and
reports `partial_release`: one formal matrix slot is verified and 35 remain
open.
See [Release governance](docs/RELEASE_GOVERNANCE.md).

The 2026-07-31 [formalization stage gate](docs/FORMALIZATION_STAGE_GATE_20260731.md)
selected formal portability to ERPNext as the next slice. That slice is now
complete; the
[ERPNext formal public-development checkpoint](docs/ERPNEXT_FORMAL_PUBLIC_DEV_CHECKPOINT_20260801.md)
records the workflow, artifact audit, repository binding and remaining
scientific limits. The same provider-free protocol has now admitted a fresh
Kubernetes public-development instance through formal input freeze; the
[Kubernetes continuation checkpoint](docs/KUBERNETES_FORMAL_CONTINUATION_GATE_20260801.md)
records the linked source and continuation runs. The next slice is explicit-scope
execution control against those frozen inputs. Model-consumed development
scenarios will not be relabeled as release data.

## Cross-model native results

### Current hard-family development result

The ERPNext sales-return family has a valid paired GLM-5.2 experiment at the
same source commit, but is currently excluded from the canonical manifest
until its referenced raw runtime evidence is archived:

| Condition | Recovery Integrity | Matched-group | Goal completion | Tool/provider/runtime errors |
|---|---:|---:|---:|---:|
| Explicit correct scope | 4/4 | 1/1 | 4/4 | 0 |
| Ordinary recovery | 2/4 | 0/1 | 4/4 | 0 |

The two ordinary failures both created one duplicate replacement invoice, but
the causal errors differed. In one state the invoice already existed at the
failure boundary and the model never queried it. In the no-commit state, the
model submitted a Delivery Note that triggered invoice creation, then failed
to refresh state before executing its previously planned create call. This
second pattern is a recovery-time plan-invalidation failure, not merely an
incorrect initial diagnosis. These are four development trials, not a stable
model ranking. Evidence is archived under
`data/evidence/erpnext-sales-return-{control,ordinary}-20260730`.

### Historical candidate-family comparison

Two valid GitHub Actions jobs ran the same easy pilot and frozen hard holdout
with ordinary public tools and a 15-turn budget:

| Model | Easy Integrity | Hard Integrity | Hard matched-group | Hard goal completion | Provider/runtime errors |
|---|---:|---:|---:|---:|---:|
| GLM-5.2 | 20/20 (100%) | 6/20 (30%) | 0/5 | 20/20 | 0 |
| DeepSeek-V4-Pro | 20/20 (100%) | 5/20 (25%) | 0/5 | 20/20 | 0 |

Both models reliably solved the no-commit variant and failed most or all
already-committed variants. All 29 combined hard failures completed the visible
business goal but left a duplicate replacement invoice. GLM-5.2 omitted the
linked-invoice investigation in all 14 failures. DeepSeek-V4-Pro issued more
queries overall, but 13 failures still omitted that investigation and two used
an invalid direct filter, received an explicit tool error, and then created a
new invoice anyway.

The replayed reference recovery and explicit-scope execution control both pass
all four variants. This historical cross-model result therefore isolates a reproducible
post-commit downstream-effect investigation failure rather than inability to
execute the tools, but it is not counted as a current hard-split result. Valid
experiment runs:

- [GLM-5.2 `30407901921`](https://github.com/fengyw23/AftermathBench/actions/runs/30407901921);
- [DeepSeek-V4-Pro `30415045805`](https://github.com/fengyw23/AftermathBench/actions/runs/30415045805).

Sanitized trajectories are retained under `data/evidence/erpnext-*-final-valid-20260729`.

## Quick start

Python 3.12 or newer is required.

```bash
python -m unittest discover -s tests -v
python -m aftermath_bench validate
python -m aftermath_bench status
python -m aftermath_bench validate-release
# Expected to fail until every formal slot is closed:
python -m aftermath_bench validate-release --require-full
python -m aftermath_bench validate-runtimes
python -m aftermath_bench validate-native-scenario --help
python -m aftermath_bench demo --all
python -m aftermath_bench demo-release --all
python -m aftermath_bench demo-itsm --all
python -m aftermath_bench baselines
python -m aftermath_bench fetch-enterpriseops
python -m aftermath_bench run-itsm-suite --help
python -m aftermath_bench run-erpnext-model --help
python -m aftermath_bench run-native-model --help
```

When running directly from a checkout without installing the package:

```bash
set PYTHONPATH=src
python -m aftermath_bench validate
python -m aftermath_bench status
python -m aftermath_bench validate-runtimes
python -m aftermath_bench validate-native-scenario --help
```

On PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m aftermath_bench validate
python -m aftermath_bench validate-runtimes
python -m aftermath_bench demo --all
python -m aftermath_bench demo-release --all
python -m aftermath_bench demo-itsm --all
python -m aftermath_bench baselines
python -m aftermath_bench fetch-enterpriseops
python -m aftermath_bench run-itsm-suite --help
python -m aftermath_bench run-erpnext-model --help
python -m aftermath_bench run-native-model --help
```

## Design principles

- **Relevant-state complexity, not database size.** Admission checks operate on
  the task-specific causal recovery graph.
- **Matched transition faults.** A shared prefix and surface error conceal
  different true commit semantics.
- **Authoritative investigation.** Correct recovery requires querying multiple
  state sources before mutation.
- **Persistent consequences.** Blind retries can create duplicate or otherwise
  unsafe effects.
- **Deterministic evaluation.** State predicates, event milestones, and
  minefields replace an LLM judge.
- **Multiple legal trajectories.** The evaluator checks recovered integrity,
  not imitation of a reference action order.
- **Fully inspectable semantics.** Formal tasks require server, schema,
  transaction, reset, fault, and evaluator evidence that reviewers can audit.

See [Benchmark Specification](docs/BENCHMARK_SPEC.md) and
[Task Schema](docs/TASK_SCHEMA.md). The current upstream integration findings
are documented in
[EnterpriseOps-Gym Integration Audit](docs/ENTERPRISEOPS_AUDIT.md). The
implemented-versus-planned boundary is tracked explicitly in
[Pilot Implementation Status](docs/PILOT_STATUS.md). Model-provider setup,
model-visible inputs, and trajectory contents are specified in
[Model Experiment Protocol](docs/MODEL_EXPERIMENTS.md).
The substrate decision and source evidence are documented in
[Fully Open Runtime Selection](docs/OPEN_RUNTIME_SELECTION.md).
The native hard-task recipe and experiment audit are documented in
[Hard Task Construction](docs/HARD_TASK_CONSTRUCTION.md) and
[GLM-5.2 24-Hour Report](docs/GLM52_24H_REPORT.md).

`python -m aftermath_bench status` is the machine-derived source of truth for
the boundary between the 183-case target matrix and locally implemented
scenarios. In particular, a replay-admitted development scenario is not
reported as a formal release case unless it also uses an execution-admitted
runtime and belongs to a `public_dev` or `hidden_test` split.
