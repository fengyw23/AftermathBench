# Release governance

## Why a separate release manifest exists

`data/benchmark_matrix.json` specifies the intended benchmark portfolio. It is
not evidence that any task has been implemented. `data/release_manifest.json`
binds concrete scenarios and evidence to that design.

This separation prevents three invalid claims:

1. an internally consistent design table being reported as released data;
2. an unrelated hard scenario being counted under a similarly named family;
3. one public or hidden scenario making the whole benchmark appear ready.

## Canonical identity

Every active scenario has independent identifiers:

```text
domain_id / family_id / instance_id / variant_id
```

`scenario_id` remains a stable artifact name, but it is not parsed to infer
these fields. In the current scenario JSON, the serialized field is `family`
and the normalized `NativeScenario.family_id` property exposes it as
`family_id`; `variant_id` is serialized as each `matched_variants[].id`. A
formal slot is:

```text
domain_id/family_id/instance_id
```

The slot's domain, family, instance and split must exactly match the matrix.

## Development checkpoint

`aftermathbench-2026.08-r1` currently binds one formal public-development
slot in each native domain:

| Domain | Family | Instance | Variants |
|---|---|---:|---:|
| ERPNext | `erpnext-sales-return-exchange-reconciliation` | `dev-001` | 4 |
| Forgejo | `forgejo-release-package-publication` | `dev-002` | 8 |
| Kubernetes | `k8s-constraint-interaction-recovery` | `dev-006` | 13 |

Each binding verifies:

- canonical scenario identity and unique variant IDs;
- exact family-specific variant count;
- per-variant boundary and recovery-signature classes, including the required
  family-specific diversity;
- scenario and admission-artifact SHA-256 values;
- hard admission recomputed from the bound artifacts;
- source/runtime execution admission;
- supplied-scope control coverage, zero run errors, and at least 80% pass,
  recomputed from individual reports rather than trusted from summary fields.

Admission uses an acyclic evidence chain. The core validator hashes only the
evidence it consumes (`prefix`, `reference`, graph, baselines, and any declared
replay or projection evidence). It does not consume its own derived
`admission.json`. The release verifier then separately requires that the
stored report exactly equals the canonical recomputation and that the release
manifest binds the report file's SHA-256. A stale or edited report therefore
fails release validation even if its file hash declaration is also updated.

The model-consumed ERPNext sales-return/exchange development scenario remains
an explicit historical exclusion. Its legacy runtime manifests reference an
older evidence protocol and cannot be promoted by relabeling the split. The
checkpoint still contains 21 verified development-candidate cases, separate
from the four cases in the fresh formal public-development slot.

The subsequently recovered GitHub Actions JSON is preserved under
`data/evidence/erpnext-sales-return-native-historical-30425865276/` for
scientific auditability. Its machine-readable provenance deliberately marks it
as historical-only and non-formal: the legacy reports document four native
boundaries and successful deterministic recoveries, but lack the reset
snapshots and cross-bound formal evidence envelope required by the current
gate. Archiving them does not change ERPNext's release eligibility.

The manifest is valid and derives `partial_release`. It binds one formal
ERPNext public-development slot, has zero hidden tests, and leaves 35 of the 36
target slots open.

## Formal release states

The verifier derives the state; a manifest cannot simply declare it.

```text
no formal slot
  -> development_only

some formal slots, or any open gate
  -> partial_release

all required slots exactly covered
AND all bindings verified
AND release_stage == formal
  -> full_release_ready
```

A formal binding additionally needs distinct evidence envelopes for the
boundary bundle, reference bundle, tool contract, evaluator, reset evidence,
raw-run archive, and execution-control record. Every envelope binds the same
release/scenario/instance/variant identity and its payload files. Directed
dependency hashes bind the reference and model runs to their boundary, tool,
evaluator and reset inputs, and bind execution-control evidence to the raw-run
archive. Distinct filenames are not sufficient: each role has a typed payload
contract, and the verifier recomputes the reset-to-boundary, boundary-to-
reference, raw-run-to-summary, and execution-control relationships. Empty or
role-renamed payloads therefore cannot satisfy a formal slot.

The seven envelopes are necessary but no longer sufficient. A formal slot
also binds the completed declarations manifest by path and SHA-256. That
manifest binds the immutable five-role pre-provider lock, the one common
model-visible prefix, the exact native failure report per variant, each
unabridged control trajectory, and the execution-control summary. Promotion
recomputes a registered pure family evaluator from each reference terminal
state and raw control trajectory. Consequently, self-consistent but fabricated
`passed: true` fields cannot promote a task; an unknown evaluator family is
also rejected.

A hidden binding also needs a fully verified active freeze. The attestation
must hash the exact active scenario and instance specification; its usage
ledger uses a sequence-numbered SHA-256 chain and the release manifest binds
the exact ledger file hash. The formal native runner atomically appends
`evaluation_locked` before its first provider request and fails closed when
the freeze, ledger, model, condition, or evaluation identity does not match.
The same locked evaluation may continue across the scenario's variants; its
last run appends `consumed`. Hidden lifecycle changes are therefore enforced
by the runner rather than an optional bookkeeping script.

Runtime admission uses a separate versioned evidence contract. It fixes the
phase-specific file, hash, and pass fields; requires unique boundary and
reference paths; and rechecks each raw payload's scenario, variant, phase
shape, and terminal pass result. In particular, a generic `passed: true`
cannot override an explicit failed reference recovery.

## Known open evidence work

The domain-neutral formal-spec protocol has now been applied to a fresh
ERPNext public-development replay. Its four native failure boundaries,
references, fixed-policy runs, execution controls and seven role envelopes are
repository-bound and independently revalidated. The two selected
model-consumed development scenarios remain non-formal, and no hidden-test
instance exists.

The next release slice applies the same protocol to a fresh Kubernetes
public-development instance. Every promoted slot must continue to bind frozen
failure-boundary source trajectories to the exact collector, tool contract,
evaluator, reset, raw-run and control artifacts. The completed ERPNext slice
and remaining limits are recorded in
`docs/ERPNEXT_FORMAL_PUBLIC_DEV_CHECKPOINT_20260801.md`.

Run:

```bash
python -m aftermath_bench validate-release
python -m aftermath_bench status
python -m aftermath_bench validate-release --require-full
```

The last command is expected to fail for the current partial-release
checkpoint because 35 formal slots and all hidden-test lifecycles remain open.
