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

`aftermathbench-dev-2026.08-r1` contains two selected hard candidates:

| Domain | Family | Instance | Variants |
|---|---|---:|---:|
| Forgejo | `forgejo-release-package-publication` | `dev-002` | 8 |
| Kubernetes | `k8s-constraint-interaction-recovery` | `dev-005` | 13 |

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

ERPNext sales-return/exchange remains structurally hard-admitted, but its
legacy runtime manifests reference boundary and recovery files that were not
archived. The runtime gate therefore rejects it and the release manifest lists
it as an explicit exclusion. The checkpoint contains 21, not 25, verified
development cases.

The manifest is valid, but its release state is `development_only`. It binds
zero formal slots, has zero hidden tests, and leaves all 36 target slots open.

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
archive.

A hidden binding also needs a fully verified active freeze. The attestation
must hash the exact active scenario and instance specification; its usage
ledger uses a sequence-numbered SHA-256 chain and the release manifest binds
the exact ledger file hash. Any model access makes the instance ineligible.

## Known open evidence work

The current replay projections are sufficient for the existing structural
admission tests, but they are not yet a formal evidence closure. They must next
be bound to frozen failure-boundary source trajectories, collector/tool
contract hashes, and explicit phase labels. This prevents reference-terminal
state from being mistaken for evidence that was visible before the first
recovery write.

Run:

```bash
python -m aftermath_bench validate-release
python -m aftermath_bench status
python -m aftermath_bench validate-release --require-full
```

The last command is expected to fail for the current development checkpoint.
