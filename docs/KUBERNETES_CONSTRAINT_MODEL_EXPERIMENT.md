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
