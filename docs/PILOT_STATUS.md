# Pilot Implementation Status

## What is executable now

| Workflow | Prefix provenance | Persistent state carriers | Matched faults | Deterministic evaluation |
|---|---|---|---|---|
| Enterprise employee transfer | Six public environment write tools | Prototype enterprise state store | no commit, response lost, partial, async | Yes |
| Release and database migration | Six public environment write tools | Real Git repository, two SQLite databases, registry file | no commit, response lost, partial, async | Yes |

Both workflows begin from a clean state, replay the successful prefix, inject
the ambiguous failed transition, and mark a fixed failure boundary before
recovery begins.

## Important limitation

The current enterprise workflow uses AftermathBench's executable prototype
state store. Its table and relation design is informed by enterprise
benchmarks, but it is not yet running inside an EnterpriseOps-Gym MCP
container.

The release workflow already uses independent, persistent state carriers. It is
not a text-only simulation, although its deployment control plane is local
rather than Kubernetes.

## Next four enterprise workflows

Candidate workflows will only be admitted after their component writes and SQL
state deltas are verified:

1. ITSM major-incident escalation:
   incident, affected CIs, SLA replacement, child incidents, notification, and
   audit state.
2. HR offboarding across identity and collaboration:
   HR case, checklist tasks, group membership, Drive permission, calendar
   ownership, and notification.
3. CSM entitlement and installed-product correction:
   customer case, contract, entitlement, installed product, case SLA, and
   interaction history.
4. Change/problem closure:
   problem, linked incidents, change request, configuration items, knowledge
   publication, and SLA state.

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

