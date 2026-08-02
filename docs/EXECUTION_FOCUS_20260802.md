# Execution focus from 2026-08-02

## Decision

The research question and three-domain scope remain unchanged. The execution
priority changes from strengthening individual evidence paths to producing
formal release coverage at a sustainable rate.

The current machine-derived baseline is:

- 36 target slots and 183 target matched cases;
- 10 implemented scenarios and 53 implemented matched cases;
- 6 hard-admitted scenarios and 37 hard-admitted matched cases;
- 1 formally bound slot and 4 formally bound matched cases;
- 0 frozen hidden-test instances.

Only the last two numbers measure release completion. Development cases are
useful design evidence but cannot be presented as released benchmark data.

## Milestones and time boxes

| Milestone | Deliverable | Target window |
|---|---|---:|
| M0 | Complete Kubernetes K3/K4/K5 and freeze the formal protocol | 1–2 days |
| M1 | Formal public slots in all three domains | 1 week |
| M2 | One fully frozen, untouched hidden lifecycle | 2 weeks |
| M3 | All 12 public-development slots and all missing families | 6 weeks |
| M4 | All 24 hidden slots frozen and formally replayed | 10–12 weeks |
| M5 | Cross-model runs, analysis and release materials | 14–18 weeks |

The windows overlap after M2. They assume shared builders and parallel CI. If
each instance keeps receiving a bespoke workflow or evidence protocol, the
full release will exceed this schedule.

## Stop rules

A detail may interrupt the active milestone only when it can change a score,
hide required evidence, break replay, contaminate a hidden split, expose a
secret or invalidate a release claim. Other issues are logged and deferred.

After M0, a proposed protocol change must identify:

1. the concrete invalid result it prevents;
2. at least two future slots that need the change; and
3. why quarantine or a local adapter is insufficient.

Without all three, keep the shared protocol frozen and continue constructing
release instances.

## Weekly progress review

The weekly review uses `python -m aftermath_bench status` and reports only:

- formal slots added;
- formal matched cases added;
- hidden instances frozen without provider access;
- matrix families completed;
- valid model runs after data freeze;
- shared blockers opened or closed.

If a week adds no formal slot, hidden instance or missing family, the following
week must begin with a scope audit before further infrastructure work.
