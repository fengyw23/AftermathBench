# ERPNext shared-batch ordinary GLM-5.2 evidence

- GitHub Actions run: `30881911583`
- Source branch: `erpnext-shared-batch-model`
- Source revision: `60dfd65`
- Scenario: `erpnext-shared-batch-recovery-dev-001`
- Model: `glm-5.2`
- Repetitions: one matched group of four ambiguous boundaries
- Provider or infrastructure errors: zero

The model passed two of four variants (`50%` task pass) and failed the matched
group. Goal completion and preservation were `100%`; repair completeness and
protocol safety were `50%`.

Both failures are substantive execution errors. The model inspected the
authoritative state and completed the corrective manufacturing branch, but it
enqueued a second certificate webhook while an existing delivery owner was
already pending. The idempotent receiver kept one logical certificate, yet
recorded two delivery attempts, so the strict exactly-once protocol check
failed. In both trajectories the model's own final explanation incorrectly
described two identical attempts as "exactly once". This distinguishes
business-state completion from recovery-protocol integrity rather than relying
on a formatting or termination requirement.
