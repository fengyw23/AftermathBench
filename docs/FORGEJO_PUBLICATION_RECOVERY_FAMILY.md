# Forgejo publication recovery family

## Status

`forgejo-release-publication-dev-002` is a hard-admitted development family
implemented against the pinned `forgejo-main` runtime. The source-level
implementation, closed tool schemas and deterministic evaluator are covered
by tests. Native replay produced 21 successful prefix writes, eight passing
reference recoveries, 30/30 replayed semantic relations and a maximum fixed
policy pass rate of 2/8. The admitted scenario is archived under
`data/scenarios/forgejo-release-publication-dev-002`.

## Recovery question

An approved release-bundle publication call returns the same connection
error in every case. Before that call, the Pull Request, linked issue, release
branch, publication manifest, prior release and two webhook configurations
already exist. After the error, the authoritative system may contain:

- no target Release, or one committed target Release;
- zero or one already-uploaded approved attachment;
- an independently delivered, accepted-but-response-lost, or missing
  release-coordinator event;
- an independently delivered, accepted-but-response-lost, or missing
  provenance-registry event.

The agent must reconstruct these effects from ordinary Forgejo records and
the downstream idempotency ledger, publish only missing artifacts, replay only
a failed delivery whose external effect is absent, close the release
milestone, and preserve unrelated work.

This is not a hidden-label classification task. Every scored fact is available
through the public tools, while the hidden variant identifier and a global
repair summary are not exposed.

## Native state and operations

The prefix is built exclusively through native Forgejo operations:

- repository, milestone, issue, branches, files and Pull Requests;
- one approved merge;
- a prior Release and prior Release attachment;
- branch protection;
- two `release` webhooks connected through separately faultable gateways.

The target Release, target attachments, milestone state and native webhook
history are stored by Forgejo. Receiver attempts and their idempotent effects
are stored in an independent SQLite-backed service keyed by
`X-Forgejo-Delivery`.

Model-visible mutations map to ordinary domain writes:

- create one Release;
- attach one existing repository file to one Release;
- replay one native delivery UUID;
- close one milestone.

The attachment wrapper performs a bounded source-file read followed by one
native attachment write. It does not select a missing file or recommend a
repair.

## Matched states

All eight variants expose:

> HTTP connection lost before publication completion was acknowledged.

The correct mutations differ:

| Variant | Release | Pre-existing asset | Missing external branch | Required write pattern |
|---|---|---|---|---|
| request not reached | absent | none | both effects absent because no event exists | create Release, upload 3 assets, close milestone |
| both delivered | present | none | none | upload 3 assets, close milestone |
| coordinator accepted; provenance missing | present | none | provenance | replay provenance, upload 3 assets, close milestone |
| coordinator missing; provenance accepted | present | none | coordinator | replay coordinator, upload 3 assets, close milestone |
| both missing; binary present | present | binary | both | replay both, upload checksum and SBOM, close milestone |
| coordinator delivered; provenance missing; checksum present | present | checksum | provenance | replay provenance, upload binary and SBOM, close milestone |
| coordinator missing; provenance delivered; SBOM present | present | SBOM | coordinator | replay coordinator, upload binary and checksum, close milestone |
| both accepted with lost responses | present | none | none | upload 3 assets, close milestone |

“Accepted with lost response” deliberately differs from “request did not
reach the receiver”: both appear as failed in Forgejo history, but only the
latter may be replayed safely. The external delivery UUID correlation is
therefore necessary.

Every variant requires at least four native writes. Across the group, release
creation, attachment count and webhook replay scope all vary.

## Deterministic scoring

`Recovery Integrity Pass` requires all four components:

1. **Goal completion** — one target Release from the approved branch, exactly
   the three manifest assets with byte-matching SHA-256 values, both receiver
   effects, and a closed release milestone.
2. **Repair completeness** — the complete artifact and two-consumer closure
   is present, not only the main Release record.
3. **Preservation** — the unrelated Pull Request and issue, prior Release and
   attachment, both webhooks and branch protection remain intact.
4. **Protocol safety** — no duplicate target Release or attachment, a bounded
   one- or two-row native history chain per consumer, and exactly one external
   effect with one attempt in each chain. A necessary replay creates the
   second native UUID; an unnecessary or repeated replay creates an extra
   external effect and fails.

No LLM judge or prescribed tool sequence is used.

## Admission gate

The generated scenario may enter the hard split only if:

- every boundary is materialized by the live runtime and shares the same
  visible error;
- the public-tool reference passes all eight states;
- every replay graph edge has executable evidence;
- the minimum reference needs at least four mutations and multiple evidence
  groups;
- at least three recovery signatures and two varying action branches exist;
- no fixed baseline reaches 50% and none solves the matched group.

The live workflow retains all boundaries, reference traces, fixed-policy
traces, terminal evidence, source verification, admission report and a
relative-path SHA-256 manifest.
