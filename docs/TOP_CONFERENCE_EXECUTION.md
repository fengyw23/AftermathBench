# Top-conference benchmark execution plan

## Research question

After a step in a long-running agent workflow returns an error, can the agent
interact with the real system to reconstruct the post-error state, identify
which effects and downstream obligations already exist, and complete a repair
that is neither destructive nor incomplete?

The benchmark does not assume that the failed operation was a write, that the
request definitely reached the server, or that rollback is the right repair.
An error can correspond to no durable effect, a committed primary effect, a
missing downstream effect, or an asynchronous continuation that is still
pending.

## What is executable today

The repository has nine active development scenarios and 49 matched states.
Five scenarios (33 states) pass structural hard admission. After replaying the
files named by each runtime manifest, four hard scenarios remain on
execution-admitted runtimes.

The canonical development manifest deliberately selects only two of them:

- Forgejo release/package publication: 8 matched states;
- Kubernetes constraint-interaction recovery: 13 matched states.

They supply 21 verified development cases. The Forgejo reference passes 8/8
and the strongest fixed policy passes 2/8. The Kubernetes reference passes
13/13, its explicit-scope control passes 12/13, and ordinary GLM-5.2 recovery
passes 1/13. Neither scenario occupies a formal release slot.

ERPNext sales-return/exchange is structurally hard-admitted and has useful
model trajectories, but its older CI summaries name raw boundary and reference
files that were not archived in the repository. The stricter runtime gate now
rejects that missing evidence, so ERPNext is not counted in the canonical
development manifest until the native run is reproduced and archived. The
historical purchase-return holdout remains a consumed regression instance and
cannot support an unseen-test claim.

## Hard Admission v2

A formal hard family must satisfy all of the following from executable
artifacts:

- at least eight task-relevant successful prefix writes;
- at least 20 relevant native entities and eight relation types;
- dependency depth at least five;
- at least four independent evidence sources;
- all counted relations replay successfully from native evidence;
- no single query identifies every matched state;
- at least four state-changing recovery operations in every state;
- at least two downstream repairs and two protected shared dependencies;
- at least three dangerous but executable incorrect plans;
- at least three distinct semantic recovery signatures;
- variation across at least two independent action branches;
- reference recovery passes every state;
- fixed heuristics do not solve the matched group.

The graph file can no longer satisfy admission with an author-written
`observed: true`. Each edge must contain selectors and deterministic
assertions, and each assertion is replayed across all captured states.

## Dataset matrix and release control

`data/benchmark_matrix.json` fixes the target portfolio:

- ERPNext, Forgejo, and Kubernetes;
- four task families per domain;
- one public development instance and two hidden instances per family;
- an explicit family-specific matched-state count for every family;
- 183 executable cases in the current target (most families use four states,
  Forgejo publication uses eight, and Kubernetes constraint interaction uses
  thirteen).

Every family declares a real native operation that reports an error, the
native objects involved, protected prior effects, at least two independent
downstream branches, and at least three expected recovery signatures. The
matrix validator prevents silent scale drift, duplicate canonical slots, and
simple one-state or one-branch tasks from being counted toward the release
target. The `top-conference-full` scale and exact slots are fixed in verifier
code rather than trusted from matrix self-declarations. A bound scenario must
also annotate every variant with a known boundary class and recovery-signature
class, then meet the family-specific diversity minimum.

`data/release_manifest.json` is separate from this design matrix. It binds
implemented scenario identities, variant sets, admission artifacts and
execution-control evidence by hash. Release state is:

- `development_only` when no formal slot is bound;
- `partial_release` when some but not all formal slots are verified;
- `full_release_ready` only when every matrix slot is bound exactly once and
  all runtime, hard-admission, evidence-closure and hidden-test lifecycle gates
  pass.

One hard `public_dev` scenario can therefore never make the whole benchmark
appear release-ready.

## Immediate build order

1. Re-run ERPNext sales-return/exchange and archive every boundary/reference
   file named by its runtime manifest; only then restore it to the canonical
   development manifest.
2. Convert the Forgejo and Kubernetes candidates to the formal evidence
   envelope contract, including distinct boundary, reference, tool, evaluator,
   reset, raw-run, and execution-control artifacts with dependency hashes.
3. Materialize fresh `public_dev` instances rather than relabeling model-seen
   development scenarios.
4. Add ERPNext manufacturing-rework and multi-warehouse-transfer, Forgejo
   package-provenance and migration/deployment, and the remaining Kubernetes
   families under the same semantic-profile gate.
5. Generate two independent hidden instances per family, freeze their exact
   bundles, and commit the hash-chained usage ledger before provider access.
6. Run the complete 36-slot release validator and publish only when every
   formal slot is independently verified.

Any scenario used for hidden-test reporting must declare `hidden_test`,
`hard`, and `hidden_test_eligible: true`, and must have an active freeze.
Workflows reject historical, consumed, or development instances before the
expensive runtime build.

The release target is currently 183 cases, but a family enters the formal score
only after its reference program, execution control, evidence replay, reset,
and hard-admission checks all pass.
