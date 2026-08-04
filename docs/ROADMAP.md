# Roadmap

## Phase 0 - executable recovery scaffold (complete)

- Hard-task schema and structural admission validator.
- Deterministic integrity evaluator.
- Matched no-commit, response-loss, partial-commit, and asynchronous variants.
- Enterprise transfer and release/database-migration prototypes.

## Phase 1 - full-seed ITSM concept slice (frozen)

- Pinned and verified the EnterpriseOps-Gym ITSM seed.
- Materialized all 24 upstream tables and 241 seed rows.
- Added six-write prefix replay, hidden variants, 16 model-visible tools,
  fourteen SQL checks, model adapters, and complete trajectory logging.
- Tagged as `v0.2.0`.

This phase is a concept prototype. EnterpriseOps-Gym does not publish the
domain server and native transaction implementation, so it will not be
promoted into the final native-runtime benchmark.

## Phase 2 - fully open runtime gate and source audit (complete)

- Require public server, schema, transaction, build, reset, fault, and evaluator
  evidence.
- Mark EnterpriseOps and the local release environment as legacy prototypes.
- Select ERPNext/Frappe as the primary enterprise runtime.
- Select Forgejo as the primary coding/DevOps runtime.
- Select Kubernetes as a native infrastructure-runtime stress-test substrate.

## Phase 3 - native ERPNext vertical slices (active)

- [x] Define the digest-pinned ERPNext/Frappe/MariaDB/Redis stack.
- [x] Create the seven-write procurement prefix through public APIs.
- [x] Implement request suppression, lost response, post-commit enqueue
  failure, and queued-worker-pending controls.
- [x] Implement SQL/Redis/audit reset and deterministic terminal checks.
- [x] Record gateway correlation events, queue state, remittance attempts,
  document state, stock ledger, and GL evidence.
- [x] Complete the first source build and four native replays.
- [x] Add restricted model-visible investigation and repair tools.
- [x] Pass scripted end-to-end recovery controls.
- [x] Connect the native environment to the provider-agnostic model loop.
- [x] Run the first four-state GLM pilot and attribute model behavior.
- [x] Add the sales-return/exchange family, which passes Hard Admission v2 and
  requires customer-return, credit, replacement, receipt-preservation, and
  reverse-logistics closure.
- [x] Validate the sales-return family with a four-state explicit-scope
  execution control (4/4 Recovery Integrity Pass, zero provider/runtime
  errors).
- [x] Audit the corresponding ordinary model condition and separate
  investigation, state-inference, scope, execution, and verification errors.
- [x] Construct, replay, formally seal and repository-bind an independent
  public-development instance; the consumed development scenario is not a
  release case.
- [x] Freeze and consume one independent manufacturing hidden instance with a
  locked usage ledger; GLM-5.2 completed 4/4 runs, passed 3/4 tasks and failed
  the matched group without provider/runtime errors.
- [x] Parameterize and natively validate a second shared-batch business instance
  with disjoint products, a different rework quantity, and a
  two-components-per-unit BOM. Reference, conflict-probe, fixed-policy, and
  admission checks all pass in run `30881600867`; the strongest fixed strategy
  solves only 1/4 boundaries and none solves the matched group.
- [x] Implement the inventory-cost-settlement family now frozen as a validated
  instance contract. Its ambiguous Landed Cost Voucher submission must vary
  real Stock Ledger, GL, Repost Item Valuation, and external-attestation state;
  Job Card/certificate-only variants cannot satisfy this item. Four references
  and 28 fixed-policy native executions passed run `30889742165`; model control
  passed 4/4 in run `30892895880`, and ordinary GLM-5.2 passed 3/4 in
  `30895587333` but failed the matched group after duplicating an asynchronous
  external delivery.
- [x] Complete native replay of the independent inventory-cost `public-dev-002`
  instance, which uses disjoint items and 2:3 component ratios instead of the
  first instance's 1:1 topology. Run `30896418025` passes both independent
  instances, but retrospective static/adaptive depth is only 2/2; retain this
  family as a diagnostic instead of admitting it to the hard split.
- [ ] Construct and freeze two unconsumed hidden instances without model
  access.

## Phase 4 - Forgejo coding/DevOps vertical slice (active)

- [x] Build Forgejo from pinned source and archive successful four-state
  boundary and reference replay evidence.
- [x] Admit the Forgejo runtime from source and execution evidence.
- [x] Register the first PR/merge/release/webhook scenario from archived native
  replay evidence.
- [x] Demonstrate that the first scenario is an easy pilot: a compact decision
  tree solves all four matched states.
- [x] Add a hard package-publication family with two independently repairable
  downstream consumers, three independently repairable assets, and no
  family-wide fixed decision tree.
- [x] Complete and archive its task-specific model execution control and
  ordinary model condition.
- [x] Retain the 4/4 package-provenance result as a saturated control and freeze
  a separate six-boundary approved-artifact-promotion instance contract that
  crosses approval, signed artifacts, deployment, external attestation and
  prior-release preservation.
- [x] Implement and replay the approved-artifact-promotion native prefix,
  six failure boundaries and deterministic evaluator. Run `30891327568` passed
  all references and cross-system boundary checks.
- [x] Reject fixed promotion policies with 36 native executions; the strongest
  procedures pass 2/6 and no procedure solves the matched group.
- [x] Complete the corrected execution-control gate. Run `30897349405` passes
  6/6 with no provider or runtime errors. Do not spend an ordinary-model run on
  this family because replay-derived depth rejects it from the hard split.
- [x] Audit the second control run (`30895584547`): its apparent 2/6 result was
  entirely caused by an undisclosed exact verification-comment body. Keep that
  check as a diagnostic rather than a hard invariant and rerun the control.
- [x] Add replay-derived scope-decision auditing. It correctly rejects the
  six-stage promotion family as too shallow (static certificate 3, adaptive
  depth 2 versus its predeclared 5/4 profile).
- [x] Build a non-monotonic Forgejo reconciliation family whose independently
  missing or inconsistent Actions evidence, artifact registration, deployment,
  attestation and metadata force all five public evidence surfaces to matter.
- [x] Add a design-time independent-gap gate with joined-evidence accounting.
  Both the Forgejo and ERPNext target designs currently require six public
  surfaces in the worst case; native replay must reproduce this before hard
  admission.
- [x] Materialize the six Forgejo design boundaries in native Actions,
  deployment, attestation and release services, then rebuild the decision
  matrix from replay instead of accepting the design declaration. Run
  `30899866459` passes all boundaries/references and reconstructs static and
  adaptive depth 6/6 on the first instance.
- [x] Replay the disjoint `radiology-routing-service` instance and execute 84
  fixed-policy trajectories across both instances. Run `30902308186` passes all
  native gates; the strongest fixed strategy reaches 2/6 and no strategy solves
  either matched group.
- [x] Pass the task-specific GLM-5.2 execution control. Source-bound run
  `30905646467` passes 6/6 with no provider or runtime failures.
- [x] Run ordinary GLM-5.2 on the same commit and snapshots. Run `30908258071`
  also passes 6/6, proving the one-gap/one-local-repair family is saturated even
  though its replayed evidence depth is 6/6 and fixed policies fail.
- [ ] Build an interacting-gap successor whose mutation operators have
  overlapping effects and preservation conflicts; add an intervention-plan
  complexity gate distinct from evidence-query depth.
- [ ] Freeze an independent hidden package-publication instance and make
  replay identity/payload semantics explicit before any hidden model call.

## Phase 5 - Kubernetes interaction stress test (active)

- [x] Build source-audited native Kubernetes state, query, mutation, and
  evaluator layers.
- [x] Admit the Kubernetes runtime from archived source-build, reset, boundary,
  and reference-recovery evidence.
- [x] Construct a 13-state constraint-interaction family with distinct
  boundary-relative recovery directions.
- [x] Reject an invalid first execution control whose target omitted the exact
  external-event envelope.
- [x] Complete and audit the corrected execution control.
- [x] Accept the 13-state task-specific execution control after it passed
  12/13 (92.31%) with zero infrastructure and interface failures.
- [x] Launch the ordinary condition from the exact same source commit only
  after that gate passed.
- [x] Audit, archive, and compare the completed ordinary condition: 2/13
  ordinary versus 12/13 explicit-scope control, with identical task-state
  projections and zero scored infrastructure failures.

The Kubernetes interaction family uses native Kubernetes objects and public
tools, but some cross-system contracts are benchmark-authored ConfigMaps and
external-event records. It is therefore a reasoning stress test, not the sole
evidence for production realism.

## Phase 6 - hard-task expansion

- Extract a domain-neutral formal-spec adapter from the validated Forgejo
  pipeline and prove output-equivalent validation on its regression fixtures.
- Materialize a fresh ERPNext sales-return `public_dev` instance with
  per-variant reset snapshots, a pre-provider input lock and seven-role formal
  evidence before adding more development-only families.
- Apply the same adapter to a fresh Kubernetes interaction `public_dev`
  instance while preserving exact runtime-generated identities visible to the
  model.
- Add clean-state and explicitly provided-target-state controls.
- Add automatic failure attribution and trajectory comparison.
- Reject task families solved by one fixed retry/no-retry heuristic.
- Expand only through source-admitted runtimes.
- Add ERPNext manufacturing-rework and multi-warehouse-transfer families.
- Add an independent hidden Forgejo instance and a second native family
  outside release publication, crossing approval, signed artifacts, deployment,
  external attestation, and prior-release preservation.
- Freeze generic evidence, runtime, model-run, and archive schemas before
  generating release instances.

## Phase 7 - benchmark-scale evaluation

- Freeze development and hidden test splits.
- Evaluate GPT, Claude, Qwen, DeepSeek, and open-weight agents.
- Report task pass, matched-group success, component pass rates, query coverage,
  unsafe retries, preservation failures, and verification omissions.
- Release generation, contamination, and reproducibility documentation.

## Current release boundary

The planned portfolio contains 183 family-profiled cases, but the repository is still
development-only. At the latest machine-readable status checkpoint:

- nine scenarios and 49 matched post-error states are implemented;
- five scenarios and 33 matched states pass structural hard admission;
- four of the five structurally hard scenarios run on execution-admitted
  runtimes; ERPNext requires a fresh replay under the current reset and formal
  evidence contracts rather than reuse of its archived legacy reports;
- the canonical development manifest verifies two candidates and 21 cases;
- no scenario belongs to a formal `public_dev` or `hidden_test` release split.

These counts must be generated with `python -m aftermath_bench status`; they
must not be inferred from the target matrix or workflow success badges.
The exact stage decision and promotion gates are recorded in
`docs/FORMALIZATION_STAGE_GATE_20260731.md`.
