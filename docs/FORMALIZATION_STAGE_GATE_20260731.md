# Formalization stage gate - 2026-07-31

## Decision

The methodology-validation phase is complete, but the benchmark-release
phase is not. The next implementation slice must make the formal evidence
protocol portable to a second native domain. It must not add another
development-only task family and must not relabel a model-consumed instance as
`public_dev`.

The selected next slice is:

> Extract a domain-neutral formal-evidence specification adapter from the
> working Forgejo pipeline, then use it to materialize a fresh ERPNext
> sales-return public-development instance from native replay.

Kubernetes formalization follows the same adapter after this slice. This order
closes the only runtime-admission gap among the three selected domains and
tests whether the formal protocol transfers from a source-code hosting service
to a transactional ERP system before tackling the larger thirteen-boundary
Kubernetes family.

## Audited repository state

The following counts come from `python -m aftermath_bench status` at commit
`9cffc4e12ced3a22ba1af3e6afe0e98fc768ba12`, rather than from workflow badges or
the aspirational benchmark matrix:

| Property | Audited value |
|---|---:|
| Implemented scenarios | 9 |
| Implemented matched states | 49 |
| Structurally hard-admitted scenarios | 5 |
| Structurally hard-admitted matched states | 33 |
| Hard scenarios on execution-admitted runtimes | 4 |
| Selected development candidates | 2 |
| Selected development cases | 21 |
| Repository-bound formal release scenarios | 0 |
| Repository-bound formal release cases | 0 |
| Open target-matrix slots | 36 |

The release manifest is internally valid and correctly derives
`development_only`. The target matrix describes the intended 36-instance,
183-case portfolio; it is not evidence that those cases exist.

## Domain-by-domain evidence boundary

| Domain | Task evidence | Model-control evidence | Formal-release blocker |
|---|---|---|---|
| Forgejo | Eight native package-publication boundaries; reference 8/8; best fixed policy 2/8 | Supplied-scope control 8/8 | A fresh public-development workflow completed the seven-role pipeline, but its uploaded artifact is not yet bound into the repository release manifest; the consumed development scenario remains non-formal |
| Kubernetes | Thirteen native interaction boundaries; reference 13/13; best fixed policy 6/13 | Corrected supplied-scope control 12/13; ordinary GLM-5.2 1/13 | No Kubernetes formal-spec adapter, no seven-role public-development workflow, and no unconsumed public-development instance |
| ERPNext | Four native sales-return boundaries; reference 4/4; historical repeated ordinary GLM-5.2 13/20 with matched-group 0/5 | Supplied-scope control 4/4 | Runtime evidence uses the legacy protocol: no per-variant reset snapshot, current input lock, cross-bound hash closure, or seven-role envelopes |

The successful Forgejo public-development workflow is GitHub Actions run
[`30606890872`](https://github.com/fengyw23/AftermathBench/actions/runs/30606890872).
GitHub reports the uploaded artifact as
`forgejo-publication-public-dev-evidence-30606890872`, artifact id
`8784922788`, size `2,007,009` bytes, and digest
`sha256:c91f319e0ed40549cad2a19331fe9609396ebeb24761b9ec630cd37a8b44704a`.
This proves that the end-to-end workflow can seal an artifact. It does not by
itself create a repository-bound formal slot, and no result inside the artifact
is claimed here without independently importing and validating it.

## Why the next step is not "add more cases"

The current scientific result already shows task difficulty: Kubernetes
ordinary recovery passes only 1/13 while its explicit-scope control passes
12/13. The immediate bottleneck is release validity, not lack of another
difficult development example.

Adding families before formal portability would create more evidence islands:
each domain would have its own ad hoc collector, reset semantics and hashing
rules. Such a repository could report interesting model failures, but it could
not support a reproducible multi-domain benchmark release.

The existing generic `formal_evidence_builder.py` validates and seals seven
roles, but the code that derives those roles from native evidence is currently
Forgejo-specific. `forgejo_formal_build_spec.py` embeds service-specific state
capture, tool, evaluator and archive assumptions. Copying this implementation
for ERPNext and Kubernetes would make the formal contract appear common while
leaving three independent trust paths.

## Next implementation slice

### 1. Domain-neutral specification adapter

Introduce a typed adapter contract that supplies only domain-dependent facts:

- canonical scenario and variant identity;
- public tool schemas and implementation sources;
- trusted deterministic evaluator and scored state fields;
- common prefix and one reset snapshot per variant;
- exact failure report and boundary state per variant;
- reference start, unabridged reference trajectory and terminal state;
- pre-model boundary, unabridged model trajectory and recomputed control
  summary;
- runtime/source manifests and native restore bundles.

The shared layer must construct the same seven formal roles, dependency hashes,
five-role pre-provider lock and final declaration manifest for every domain.
Domain adapters may capture native state differently, but may not redefine the
role graph or trust their own `passed: true` fields.

### 2. Forgejo equivalence regression

Refactor the existing Forgejo generator through the adapter while preserving
its validation behavior. Golden-fixture tests must demonstrate that malformed
identity, phase, source, reset, trajectory and evaluator bindings continue to
fail closed. This prevents the abstraction from weakening the already working
pipeline.

### 3. Fresh ERPNext public-development instance

Generate a new sales-return instance from a parameterized instance spec. It
must use different customer, item, quantity, payment-allocation and replacement
identities from all model-consumed development evidence. It must not reuse
`erpnext-sales-return-dev-001` or merely change its split label.

For each of the four identical-surface-error variants, one CI job must:

1. build the pinned ERPNext/Frappe runtime;
2. create the prefix through public native writes;
3. freeze the database, queue and external receiver reset state;
4. execute and capture the exact failure boundary;
5. restore that exact boundary for the deterministic reference, every fixed
   policy and every model trajectory;
6. recompute terminal evaluations from native documents, ledgers, jobs and
   receiver records;
7. build the five input roles before the first provider request;
8. run the supplied-scope execution control;
9. seal all seven roles and a secret-scanned public artifact.

### 4. Formal promotion gate

The new ERPNext instance is eligible for a `public_dev` binding only when all
of the following hold:

- reference recovery passes 4/4;
- no fixed policy solves the matched group;
- supplied-scope execution control passes at least 80%;
- every model trajectory begins from the boundary bound by the input lock;
- the evaluator independently recomputes every claimed terminal result;
- all seven evidence envelopes and the declaration manifest validate;
- the public archive contains no credential or unrestricted diagnostic log;
- `validate-release` verifies the slot from repository-bound files.

Workflow success alone is insufficient. The release manifest remains
`development_only` until the validated evidence is intentionally imported and
bound.

## Kubernetes follow-on gate

The same shared adapter is then applied to a fresh, unconsumed Kubernetes
interaction instance. Kubernetes requires one additional design check: runtime
generated UIDs and external idempotency records visible to the model must be
bound to the exact pre-model boundary. A semantically similar reconstruction
with different object identities is not an exact replay when those identities
are part of the task contract.

The current `dev-005` result remains scientific development evidence. It must
not be promoted by changing metadata. The public-development instance must be
created from a new instance specification before model access and must produce
all thirteen boundaries, 117 fixed-policy runs, references, controls and
formal envelopes in one auditable pipeline.

## Resume condition

This audit stage is complete. The broader goal should resume by implementing
the adapter and the fresh ERPNext formal public-development slice above. It
should not resume with new task-family generation, hidden-test model calls, or
release claims.

The long-term goal remains open: after the ERPNext and Kubernetes formalization
slices, the repository still needs additional independent families, two frozen
hidden instances per family, repeated cross-model evaluation and a fully bound
36-slot release manifest.
