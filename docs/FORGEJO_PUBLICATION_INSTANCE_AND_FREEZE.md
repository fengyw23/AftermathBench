# Forgejo publication instance and freeze protocol

## Purpose

The original publication task proved one native vertical slice, but its
repository, versions, assets and graph assertions were embedded in code.
Copying `scenario.json` therefore did not create an independent instance.
This protocol makes the instance specification the single source of truth
and separates an immutable evaluator bundle from a mutable usage ledger.

## Instance generation

`ForgejoPublicationInstanceSpec` controls the scenario ID, repository,
package, branches, tags, manifest path, protected records, consumer names
and publication text. The prefix builder creates every persistent record
through native Forgejo writes and records the IDs returned by Forgejo. It no
longer assumes issue and pull-request numbers `1/2/3/4`.

The three publication files have stable semantic roles:

- `binary`;
- `checksum`;
- `sbom`.

Fault variants refer to these roles rather than development-instance file
names. The evaluator, reference policy and admission graph read the manifest
path, protected branch, protection rule, release metadata and asset roles
from the generated prefix.

Every scenario, prefix and failure report carries the same canonical
`instance_spec_sha256`. The native model runner rejects a mismatched scenario,
prefix, failure report, undeclared variant or missing Forgejo instance hash
before making a provider request.

## Public webhook contract

The ordinary tool surface now states the stable native behavior needed to
interpret replay:

1. a history UUID is the exact `X-Forgejo-Delivery` identity;
2. replay copies the stored historical payload rather than rebuilding it
   from current Release state;
3. replay creates a new delivery attempt and UUID;
4. the receiver's idempotency key is that UUID;
5. equal payload hashes do not merge two different UUIDs.

The replay result names the input as `source_delivery_uuid`; it does not
mislabel it as the new delivery. The wait tool requires a caller-supplied set
of known UUIDs and returns only a genuinely new history row correlated with
the receiver ledger.

## Exact native state bundles

A Forgejo failure state consists of two durable stores:

- the Forgejo `/data` volume;
- the downstream receiver SQLite volume.

`snapshot-bundle` and `restore-bundle` stop Forgejo, both webhook gateways
and the receiver together while archiving or restoring the two durable
stores. Reference programs, fixed policies and model controls can therefore
start from the same exact failure state, rather than reinjecting a
semantically similar boundary with new UUIDs. Gateway audit databases are
control-plane telemetry, so each restore resets them deterministically; they
are not model evidence or evaluator state.

Before any provider request, `freeze_native_bundle.py` binds:

- the private instance and model-facing scenario;
- native prefix and every failure-state bundle;
- boundary reports, references, baselines and admission artifacts;
- pinned source commit and Forgejo revision.

It emits a private file manifest/root hash and a salted public commitment.
Lifecycle changes are appended to a separate ledger:

`generated → frozen → evaluation_locked → consumed → retired`

Changing the usage status never rewrites the frozen task files.
Immediately before provider access, `verify_frozen_bundle.py` recomputes
every file hash, the root hash and the salted commitment, and rejects missing
or undeclared input files. Hidden eligibility also reads the usage ledger:
an active immutable attestation is not enough once the ledger contains
`evaluation_locked`, `consumed` or `retired`.

## Candidate workflow

`forgejo-publication-candidate.yml` reads the private instance from a GitHub
secret, performs all native validation without a model credential, freezes
the exact bundle, and only then exposes the API key to an optional
execution-control step. It uploads only the public commitment and aggregate
statistics; the raw hidden fixture, snapshots, gold evidence and trajectories
are deleted with the ephemeral runner.

Before materialization, the workflow rejects an instance whose
identity-bearing names or task text already occur in tracked public files.
Commands that can print private state or model diagnostics write only to the
ephemeral private directory, not the public Actions log. The execution
control must cover every matched variant, contain no run errors and reach at
least 80% task pass rate; model access marks the candidate consumed even if
that gate later fails.

The protocol was exercised end to end in GitHub Actions run
[`30568303895`](https://github.com/fengyw23/AftermathBench/actions/runs/30568303895).
The independent private candidate passed hard admission and reference `8/8`;
the best fixed policy reached `2/8` and no fixed policy solved the matched
group. GLM-5.2 execution control passed `8/8` with zero run errors. Only the
pre-model commitment and aggregate result were retained in
`data/evidence/forgejo-publication-candidate-control-20260731`.

An execution-control call consumes that candidate for methodology validation.
It must not later be presented as an unseen leaderboard test. Formal hidden
instances require the same protocol plus a pre-registered release matrix and
a new, unconsumed rolling test set.
