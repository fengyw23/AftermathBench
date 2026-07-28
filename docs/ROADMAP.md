# Roadmap

## Phase 0 — executable scaffold

- Hard-task schema and admission validator.
- Deterministic integrity evaluator.
- One enterprise workflow with four matched transition variants.

## Phase 1 — 32-task pilot

- 4 enterprise workflows.
- 4 software-delivery/database-migration workflows.
- 4 matched variants per workflow.
- Clean and privileged-state controls.
- Baselines: blind retry, assume-no-commit, assume-commit, reverse-all,
  downstream-redo, and query-primary-only.

## Phase 2 — native environments

- Pin and audit EnterpriseOps-Gym.
- Add an explicit transition fault proxy at real commit seams.
- Add containerized Git, PostgreSQL, registry, CI, and deployment services.
- Record real read/write sets, correlation IDs, emitted events, and transaction
  boundaries.

## Phase 3 — model evaluation

- OpenAI, Anthropic, Qwen, DeepSeek, and local OpenAI-compatible adapters.
- Full trajectory and state-diff logging.
- Failure attribution: investigation, diagnosis, repair scope, preservation,
  execution, and verification.

