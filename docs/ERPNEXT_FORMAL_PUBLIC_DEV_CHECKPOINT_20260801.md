# ERPNext formal public-development checkpoint — 2026-08-01

## Decision

The fresh ERPNext sales-return public-development slice is complete and is
repository-bound as the first formal release slot. The repository now derives
`partial_release`; it does **not** derive a complete benchmark release.

The broader goal should resume from this checkpoint by applying the same
formal protocol to a fresh Kubernetes public-development instance. It should
not rerun or tune the ERPNext public-development instance against model
outputs, and it should not claim hidden-test coverage.

## What was validated

GitHub Actions run
[`30647285786`](https://github.com/fengyw23/AftermathBench/actions/runs/30647285786)
executed commit `8adefb639a619c568f2e74a2de222929bbffc02a` and completed the
following sequence in one job:

1. materialized a fresh, model-unconsumed ERPNext business instance;
2. built the pinned ERPNext and Frappe revisions from source;
3. created the common business prefix through native writes and froze its
   database, Redis queue and external receiver state;
4. captured four identical-surface failure boundaries and replayed a passing
   reference recovery from each exact boundary;
5. ran 28 fixed-policy trajectories from independently restored boundaries;
6. recomputed strict hard admission from the native artifacts;
7. froze the five model-input evidence roles before provider access;
8. ran four GLM-5.2 supplied-scope execution controls from the locked
   boundaries;
9. completed and cross-validated all seven formal evidence roles;
10. produced a secret-scanned public archive and purged native services and
    credentials.

The execution-control summary reports 4/4 task passes, a task pass rate of
1.0, a matched-group success rate of 1.0 and no run errors. This is an
execution control, not an ordinary-condition benchmark score: the model was
given the correct recovery direction but still had to execute ordinary public
ERPNext tools.

## Public artifact audit

The uploaded artifact is
`erpnext-sales-return-public-dev-evidence-30647285786`, artifact id
`8801561958`, size `1,577,866` bytes, with GitHub digest:

```text
sha256:0be755a8039d3d849c9319b822111f50bd99aae2734eec7d083684d4ecdeeb51
```

The downloaded ZIP matched that digest. A second local audit found:

| Check | Result |
|---|---:|
| Extracted public files scanned for secrets | 343 |
| Unsafe names or secret hits | 0 |
| Files bound by the internal manifest | 342 |
| Bound public bytes | 14,141,798 |
| Native restore bundles | 5 |
| Omitted private restore files | 20 |

The omitted files are the exact database, Redis queue and two external audit
archives for the common prefix and four boundaries. They are not published;
`omissions.json` binds each omitted path, byte count, SHA-256 and owning bundle
manifest. Only the generated `repo-ready` scenario and formal evidence subtree
was imported into the repository.

## Repository-bound result

`python -m aftermath_bench validate-runtimes` now admits `erpnext-v15` by
hash-verifying the four raw native boundary reports and four raw reference
reports. The gate accepts the formal native boundary shape only when it has a
non-empty failure surface, an observed failed call, non-empty captured state,
and a separate passing boundary validation with non-empty checks.

`python -m aftermath_bench validate-release` now passes and derives:

| Property | Value |
|---|---:|
| Release state | `partial_release` |
| Implemented scenarios | 10 |
| Implemented matched cases | 53 |
| Hard-admitted scenarios | 6 |
| Hard-admitted matched cases | 37 |
| Hard scenarios on execution-admitted runtimes | 6 |
| Repository-bound formal scenarios | 1 |
| Repository-bound formal cases | 4 |
| Verified target slots | 1 / 36 |
| Open target slots | 35 / 36 |

Every check for the ERPNext binding passes: active scenario identity, matrix
mapping, variant semantics, recomputed hard admission, runtime admission,
admission artifact hashes, recomputed 4/4 execution control, formal declaration
closure and trusted evaluator replay.

## Scientific boundary

This checkpoint establishes a reusable construction and evidence method for
one native transactional ERP family. It does not establish a complete
top-conference benchmark on its own. In particular:

- there is only one formally bound public-development family;
- there is no unconsumed hidden-test instance;
- ordinary-condition cross-model experiments have not been run on a frozen
  hidden test;
- 35 target-matrix slots remain open.

The next valid slice is formal portability, not more tuning of this public
case: create a fresh Kubernetes public-development instance through the shared
adapter, freeze all boundaries before provider access, import the verified
artifact, and bind the second formal slot. Hidden instances and repeated
cross-model experiments follow only after the public construction protocol is
stable in multiple native domains.
