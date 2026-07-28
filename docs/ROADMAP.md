# Roadmap

## Phase 0 — executable recovery scaffold (complete)

- Hard-task schema and admission validator.
- Deterministic integrity evaluator.
- Matched no-commit, response-loss, partial-commit, and asynchronous variants.
- Enterprise transfer and release/database-migration prototypes.

## Phase 1 — full-seed ITSM vertical slice (implementation complete)

- Pin and verify the EnterpriseOps-Gym asset and exact ITSM seed.
- Materialize all 24 upstream tables and 241 seed rows.
- Replay a six-write prefix and inject four real state-transition outcomes.
- Verify the terminal state with fourteen task-scoped SQL checks.
- Expose closed JSON schemas for 16 model-visible tools.
- Support OpenAI-compatible and Anthropic message/tool protocols.
- Preserve complete trajectories, state fingerprints, usage, and provider
  errors without storing credentials or private reasoning.
- Run the four-state suite repeatedly and aggregate matched-group success.

The remaining Phase 1 work is empirical: run strong models and determine whether
failures come from insufficient investigation, commit-state diagnosis,
cross-record repair, preservation, execution, or final verification.

## Phase 2 — hard-task expansion

- Add three more enterprise workflows using independently sourced state graphs.
- Add three more software-delivery/database workflows with persistent state
  beyond repository files.
- Add clean-state and explicitly provided-target-state controls.
- Add automatic failure attribution and trajectory comparison.
- Reject task families solved by one fixed retry/no-retry heuristic.

## Phase 3 — native service runtimes

- Run admitted EnterpriseOps workflows against its published MCP containers
  when the required server images are available.
- Add containerized Git, PostgreSQL, artifact registry, CI, and deployment
  services.
- Record real read/write sets, correlation IDs, emitted events, transaction
  boundaries, and asynchronous job state.

## Phase 4 — benchmark-scale evaluation

- Freeze development and hidden test splits.
- Evaluate GPT, Claude, Qwen, DeepSeek, and open-weight agents.
- Report task pass, matched-group success, component pass rates, query coverage,
  unsafe retries, preservation failures, and verification omissions.
- Release task-generation, contamination, and reproducibility documentation.
