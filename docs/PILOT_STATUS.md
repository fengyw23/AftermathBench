# Pilot Implementation Status

## What is executable now

| Workflow | Prefix provenance | Persistent state carriers | Matched faults | Deterministic evaluation |
|---|---|---|---|---|
| Enterprise employee transfer | Six public environment write tools | Prototype enterprise state store | no commit, response lost, partial, async | Yes |
| ITSM major-incident escalation | Six public environment write tools | Pinned 24-table, 241-row EnterpriseOps seed plus task records and explicit recovery extensions | no commit, response lost, partial, async | Yes |
| Release and database migration | Six public environment write tools | Real Git repository, two SQLite databases, registry file | no commit, response lost, partial, async | Yes |

Both workflows begin from a clean state, replay the successful prefix, inject
the ambiguous failed transition, and mark a fixed failure boundary before
recovery begins.

## Important limitation

The employee-transfer workflow still uses AftermathBench's prototype state
store. The ITSM workflow is a stronger integration step: its primary tables,
column names, and incident/SLA/group business relations are taken from the
audited EnterpriseOps-Gym seed, while three benchmark extension tables model
the asynchronous job, recovery audit, and closure review. It still runs in
local SQLite rather than an EnterpriseOps-Gym MCP container, so it is described
as native-schema semantics, not native tool-runtime execution.

The release workflow already uses independent, persistent state carriers. It is
not a text-only simulation, although its deployment control plane is local
rather than Kubernetes.

The ITSM workflow now has OpenAI-compatible and Anthropic model adapters,
closed JSON tool schemas, a 15-turn execution loop, complete JSON trajectory
logging, fixed-state fingerprints, and fourteen task-scoped SQL verifier
checks. The full upstream seed is the default for official CLI model runs; the
minimal fixture remains available only for unit and interface tests.

## Next four enterprise workflows

Candidate workflows will only be admitted after their component writes and SQL
state deltas are verified:

1. HR offboarding across identity and collaboration:
   HR case, checklist tasks, group membership, Drive permission, calendar
   ownership, and notification.
2. CSM entitlement and installed-product correction:
   customer case, contract, entitlement, installed product, case SLA, and
   interaction history.
3. Change/problem closure:
   problem, linked incidents, change request, configuration items, knowledge
   publication, and SLA state.
4. ITSM change rollout after approval:
   change request, affected CIs, implementation tasks, outage records,
   notification, and rollback evidence.

Each workflow will be rejected if its public tool/API boundary cannot support a
verifiable matched transition family.

## Next four software-delivery workflows

1. Online schema migration and multi-batch backfill.
2. Package publication with lost registry response.
3. Multi-repository API schema and generated-client release.
4. Infrastructure apply with local state written but remote state upload
   uncertain.

Every coding workflow must include at least one persistent state carrier beyond
repository files.
