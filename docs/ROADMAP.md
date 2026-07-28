# Roadmap

## Phase 0 — executable recovery scaffold (complete)

- Hard-task schema and structural admission validator.
- Deterministic integrity evaluator.
- Matched no-commit, response-loss, partial-commit, and asynchronous variants.
- Enterprise transfer and release/database-migration prototypes.

## Phase 1 — full-seed ITSM concept slice (frozen)

- Pinned and verified the EnterpriseOps-Gym ITSM seed.
- Materialized all 24 upstream tables and 241 seed rows.
- Added six-write prefix replay, hidden variants, 16 model-visible tools,
  fourteen SQL checks, model adapters, and complete trajectory logging.
- Tagged as `v0.2.0`.

This phase is a concept prototype. EnterpriseOps-Gym does not publish the
domain server and native transaction implementation, so it will not be
promoted into the final native-runtime benchmark.

## Phase 2 — fully open runtime gate and source audit (complete)

- Require public server, schema, transaction, build, reset, fault, and evaluator
  evidence.
- Mark EnterpriseOps and the local release environment as legacy prototypes.
- Select ERPNext/Frappe as the primary enterprise runtime.
- Select Forgejo as the primary coding/DevOps runtime candidate.
- Retain τ³-bench as a possible lightweight control substrate.

## Phase 3 — native ERPNext vertical slice (current)

- [x] Define the digest-pinned ERPNext/Frappe/MariaDB/Redis stack.
- [x] Create the seven-write procurement prefix through public APIs.
- [x] Implement request suppression, lost response, post-commit enqueue
  failure, and queued-worker-pending controls.
- [x] Implement SQL/Redis/audit reset and deterministic terminal checks.
- [x] Record gateway correlation events, queue state, remittance attempts,
  document state, stock ledger, and GL evidence.
- [ ] Complete the first source build and four native replays.
- [ ] Add restricted model-visible investigation and repair tools.
- [ ] Pass scripted end-to-end recovery controls.

## Phase 4 — Forgejo coding/DevOps vertical slice

- Build Forgejo from pinned source.
- Select package publication, release/attachment, Actions, or post-receive
  transitions with source-supported transactional and asynchronous effects.
- Require persistent consequences beyond repository files.

## Phase 5 — hard-task expansion

- Add clean-state and explicitly provided-target-state controls.
- Add automatic failure attribution and trajectory comparison.
- Reject task families solved by one fixed retry/no-retry heuristic.
- Expand only through source-admitted runtimes.

## Phase 6 — benchmark-scale evaluation

- Freeze development and hidden test splits.
- Evaluate GPT, Claude, Qwen, DeepSeek, and open-weight agents.
- Report task pass, matched-group success, component pass rates, query coverage,
  unsafe retries, preservation failures, and verification omissions.
- Release generation, contamination, and reproducibility documentation.
