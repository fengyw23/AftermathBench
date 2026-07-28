# AftermathBench

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

The formal implementation uses source-built, version-pinned ERPNext/Frappe.
It provides a digest-pinned service topology, native public-API writes, real
HTTP and queue fault boundaries, full database/queue reset, ordinary domain
tools, and deterministic terminal evaluation.

Two native task levels are retained:

- `erpnext-procurement-payment-001` is the frozen easy pilot;
- `erpnext-partial-return-{dev,holdout}-001` is the hard vertical slice for
  partial return, replacement procurement, supplier credit, shared payment,
  stock/accounting consistency, and exactly-once pickup delivery.

The hard family has four matched hidden transition states behind the same
connection-loss observation. Its complexity is derived from replay artifacts,
its reference recovery passes all variants, seven fixed heuristics have zero
matched-group success, and the holdout scenario and prefix were frozen before
any model access. The repository still contains only one formal native hard
family, so it does not yet claim broad benchmark coverage.

## Quick start

Python 3.12 or newer is required.

```bash
python -m unittest discover -s tests -v
python -m aftermath_bench validate
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
