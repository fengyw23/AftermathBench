# Kubernetes constraint-scope model experiment

## Evaluation rule

The ordinary condition is not scored until an execution-only control reaches
at least 80% success. A failed control means that the target state, tool
surface, visible contracts, provider configuration or turn budget may be the
cause; it cannot be reported as evidence of recovery-scope reasoning failure.

## Invalid control run 30455645398

The first GLM-5.2 control run is archived for diagnosis but excluded from all
benchmark results. Three trajectories completed and none passed; the fourth
was lost after two provider read timeouts. The trajectories exposed benchmark
problems:

1. `registry-contract` named the compensation and release keys but omitted
   their complete payload schemas. GLM therefore omitted `compensates` from a
   compensation event and `migration_job_uid` from a release event; the
   evaluator required both hidden fields.
2. `preparation_resolution` listed legal values without defining how absence
   of a preparation event maps to `not-created`. GLM used `released` after a
   successful release publication, which was plausible under the old text.
3. the evaluator preserved the existing v1 ledger entry, but the visible
   contract did not explicitly state that non-target record fields were
   immutable. One trajectory replaced the record and changed that field.
4. the OpenAI-compatible client used a 120-second per-response timeout. One
   long GLM reasoning response exceeded it twice and produced no trajectory.

These are task-interface and provider failures, not valid model errors. Commit
`562f604` makes the compensation and release payload fields queryable, defines
the two audit-value rules, requires merge-patch preservation of existing
fields, and raises the native model response timeout to 300 seconds. A new
control run must pass before the ordinary condition is launched.

Raw evidence is under
`data/evidence/kubernetes-constraint-model-control-invalid-20260729/`.

## Corrected but incomplete control run 30458491945

After the contract correction, every completed GLM-5.2 control trajectory
passed: 3/3 tasks and all four evaluation components. The remaining matched
state, `committed_cutover_without_publication`, produced no trajectory after
two provider read timeouts. This yields 100% conditional success but only 75%
matched-state coverage, below the predeclared 80% control threshold; ordinary
results therefore remain blocked.

The workflow already rebuilt the native failure boundary inside every retry,
so the completed trajectories do not inherit unrecorded effects from a prior
attempt. Commit `1d6e705` changes only provider robustness: it raises the
per-response limit from 300 to 600 seconds. It does not change the task,
contracts, target state or evaluator. Raw evidence is under
`data/evidence/kubernetes-constraint-model-control-incomplete-20260729/`.

## Valid control run 30461762556

With the 600-second provider limit, the same GLM-5.2 control completed all four
matched states with no run errors. Task pass was 4/4, matched-group success was
1/1, and goal completion, repair completeness, preservation and protocol
safety were each 100%. This exceeds the predeclared 80% execution-control
threshold and permits the ordinary condition to be evaluated.

The ordinary run uses the same source commit `1d6e705`, snapshots, tools,
25-turn limit, provider configuration and deterministic evaluator. The only
condition change is removal of the supplied target recovery scope. Complete
control trajectories are archived under
`data/evidence/kubernetes-constraint-model-control-final-20260729/`.

## Incomplete ordinary run 30464383237

The first ordinary run produced two complete trajectories and both passed, but
the other two states produced no trajectory after provider retries. The 2/2
conditional pass is not reported as task pass or matched-group success because
half the group is missing. The missing states are
`failed_migration_without_preparation` and
`committed_cutover_without_publication`.

Commit `1ac26da` adds an infrastructure-retry subset mode. It reruns only the
missing states, still rebuilding the authoritative failure boundary before
every attempt and using the same task, model, tools, 25-turn limit and
evaluator. After the subset completes, the first valid trajectory for each of
the four states is assembled into one directory and the standard full-scenario
summarizer is rerun. Raw incomplete evidence is under
`data/evidence/kubernetes-constraint-model-ordinary-incomplete-20260729/`.

## Provisional combined ordinary result and evaluator defect

The retry subset completed both missing states. Combining the first valid
ordinary trajectory for each state and rerunning the full-scenario summarizer
produced 4/4 task pass, 1/1 matched-group success and no run errors under the
old evaluator.

Manual mutation-scope audit then found a false acceptance. In
`committed_cutover_without_publication`, GLM created a new
`prepare:orders-v2` external event that did not exist at the failure boundary,
then published the release and recorded the preparation as released. The
terminal state was internally consistent, so the old evaluator accepted it.
However, recovery had manufactured and closed an unnecessary upstream
obligation. This is over-repair, not a valid minimal integrity-preserving
scope.

The 4/4 result is therefore provisional and excluded from official reporting.
The required evaluator correction is boundary-relative: the allowed external
key set equals the keys present at the failure boundary plus only the external
effects required to close that boundary. The visible registry contract must
also state that preparation is pre-orchestration history and cannot be created
during recovery. After this correction, native admission, execution control
and ordinary evaluation must all be rerun. Provisional trajectories are kept
under `data/evidence/kubernetes-constraint-model-ordinary-provisional-20260729/`
as a regression case.

The corrected boundary-relative evaluator retrospectively scores the four
provisional terminal states as 3/4. Only
`committed_cutover_without_publication` fails, on both the manufactured
preparation history and the resulting incorrect audit interpretation. This
3/4 is a regression diagnostic, not an official model score, because that
trajectory was generated before the prohibition became model-visible.

## Boundary-relative execution control

GitHub Actions run `30470744146` evaluated commit `69d5373` after the
boundary-relative external-effect rule became both visible and scored.
GLM-5.2 again passed 4/4 states and the complete matched group with no provider
errors; every evaluation component was 100%. This confirms that rejecting
manufactured obligations does not make the target states or public tools
unexecutable. Evidence is archived under
`data/evidence/kubernetes-boundary-relative-control-final-20260730/`.

## Boundary-relative ordinary diagnostic run 30472176745

The ordinary condition at commit `69d5373` completed all four states with no
provider or runtime errors. The deterministic evaluator passed 3/4 states and
the matched group failed. Goal completion, preservation and protocol safety
were 100%; repair completeness was 75%. No trajectory manufactured an external
effect outside the boundary-relative envelope, so the new regression gate
worked as intended.

The sole failure occurred in `failed_migration_without_preparation`. GLM-5.2
queried all seven audited evidence facets before its first mutation and read
the failed migration Job's exact `metadata.uid`. It nevertheless wrote
`migration_job_uid=none` to both the recovery audit and closure event. Its
final explanation equated a failed Job with a missing Job and then declared
that interpretation verified. The causal chain is therefore state-fact
binding followed by verification failure, not missing-tool investigation or
incorrect recovery scope.

The run also exposed an input-contract ambiguity. The visible audit contract
contained `missingJobUidValue=none`, but did not explicitly say that an
existing failed Job still requires its UID. Although the field name suggests
object absence, a low score that may depend on this interpretation is not a
valid difficulty result. The 3/4 score is therefore diagnostic and excluded
from official reporting. Raw trajectories and a reproducible query/write
analysis are archived under
`data/evidence/kubernetes-boundary-relative-ordinary-diagnostic-20260730/`.

The next source revision adds a model-visible `migrationJobUidRule`: record the
exact UID whenever any matching Job object exists, regardless of succeeded or
failed status, and use `none` only when no such object exists. Because this
changes a scored input surface, native admission, execution control and the
ordinary condition must all be rerun.

## Final Job-identity-contract revalidation

All three conditions were rerun from source commit
`5cceacec02f33d24df4f0665da1bb6eeac7f3051`, where the visible audit contract
unambiguously defines the identity of failed as well as successful migration
Jobs.

- Native admission run `30474538358` passed hard admission, all 4 references,
  all 26 replayed relations, the zero-leak audit and the fixed-policy gate.
- Execution-control run `30476627530` passed 4/4 states and the matched group;
  every evaluation component was 100% and no provider/runtime error occurred.
- Ordinary run `30478083808` completed all four states without infrastructure
  errors and passed 3/4; matched-group success was 0/1.

The sole ordinary failure was
`failed_migration_without_preparation`. GLM correctly found the failed Job,
recorded its exact UID, kept the epoch-1 catalog and v1 service, and closed the
ledger and exactly-once audit event. It nevertheless kept the unused
`orders-v2` Deployment and `orders-db-v2` Secret. This violates the visible
serving contract's candidate-cleanup rule and fails only
`candidate_lifecycle_matches_commit_state`.

This is not a hidden-field or tool-execution failure: the explicit-scope
control deleted both objects successfully, while the ordinary model explicitly
read the cleanup contract and current candidate Deployment before deciding
that no candidate action was needed. The refined diagnosis is therefore a
repair-scope omission. It also contains a narrower investigation gap: the
ordinary trajectory did not query the candidate Secret before mutation.

The immutable ordinary trajectories, runner summary and reproducible refined
analysis are under
`data/evidence/kubernetes-job-uid-contract-ordinary-final-20260730/`.
The matching admission and control archives use the same prefix
`kubernetes-job-uid-contract-*`.
