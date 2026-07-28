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

This repository is an executable research scaffold. It currently contains
three workflows:

- an enterprise employee transfer;
- a multi-table ITSM major-incident escalation;
- a software release and database migration.

Each workflow contains four matched commit-state variants:

- `not_committed`;
- `commit_response_lost`;
- `partial_commit`;
- `async_pending`.

All three samples pass the hard-task admission gate. The ITSM task uses
EnterpriseOps-Gym's native public table names and business relations across
incidents, SLAs, configuration items, child incidents, knowledge, users,
groups, and notifications. The release task uses a real Git repository,
application and control-plane SQLite databases, and a content-addressed
registry manifest. The next implementation stage will add:

1. More enterprise workflows adapted from EnterpriseOps-Gym.
2. Software-delivery and database-migration workflows running in containers.
3. Model adapters and trajectory logging.

## Quick start

Python 3.12 or newer is required.

```bash
python -m unittest discover -s tests -v
python -m aftermath_bench validate
python -m aftermath_bench demo --all
python -m aftermath_bench demo-release --all
python -m aftermath_bench demo-itsm --all
python -m aftermath_bench baselines
```

When running directly from a checkout without installing the package:

```bash
set PYTHONPATH=src
python -m aftermath_bench validate
```

On PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m aftermath_bench validate
python -m aftermath_bench demo --all
python -m aftermath_bench demo-release --all
python -m aftermath_bench demo-itsm --all
python -m aftermath_bench baselines
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

See [Benchmark Specification](docs/BENCHMARK_SPEC.md) and
[Task Schema](docs/TASK_SCHEMA.md). The current upstream integration findings
are documented in
[EnterpriseOps-Gym Integration Audit](docs/ENTERPRISEOPS_AUDIT.md). The
implemented-versus-planned boundary is tracked explicitly in
[Pilot Implementation Status](docs/PILOT_STATUS.md).
