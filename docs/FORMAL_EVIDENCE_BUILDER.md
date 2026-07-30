# Formal evidence builder

`scripts/build_formal_evidence.py` turns one strict JSON build specification
into the seven hash-bound evidence roles required by
`validate_formal_evidence_roles`.

It is a packager, not a promotion command. It:

- accepts only an active `public_dev` or `hidden_test` scenario;
- verifies scenario, domain, family, instance and variant identities against
  that scenario;
- requires `producer_commit` to equal the checked-out Git commit;
- rejects identity fields supplied inside role payloads;
- computes every file and envelope hash itself;
- freezes the five task-input roles before any provider request;
- verifies every frozen input byte again before accepting run evidence;
- validates the seven-role result with the authoritative release validator;
- publishes each phase with one atomic directory rename;
- never edits `data/release_manifest.json`.

Passing the builder does not make old development evidence formal. The normal
release-slot admission, runtime, control and hidden-lifecycle gates remain
independent requirements.

## Commands

```console
# Before the first model/provider request:
python scripts/build_formal_evidence.py \
  --spec data/formal_build_specs/<scenario>.json \
  --phase inputs

# After fresh execution-control runs have been archived:
python scripts/build_formal_evidence.py \
  --spec data/formal_build_specs/<scenario>.json \
  --phase complete

# Local convenience; internally performs the same two phases:
python scripts/build_formal_evidence.py \
  --spec data/formal_build_specs/<scenario>.json \
  --phase one-shot
```

The build spec schema is
`schemas/formal-evidence-build-spec-v1.schema.json`. Its identity is bound to
`scenario_path`. A repeated invocation is accepted only when its recomputed
output is byte-identical to the published phase.

## Role inputs

Each role contains:

```json
{
  "primary_payload": {},
  "support_files": [
    {
      "path": "data/formal/.../roles/<role>/support/capture.json",
      "source_path": "data/raw_runs/capture.json"
    },
    {
      "path": "data/formal/.../roles/<role>/support/state.json",
      "json_content": {}
    }
  ]
}
```

`source_path` copies bytes from an existing repository file. `json_content`
renders deterministic JSON. Exactly one content source is required. Every
output support path must be unique, remain under the owning role's `support/`
directory and be hash-referenced by that role's primary payload.

Support sources are restricted to auditable repository roots: `data/`,
`runtimes/`, `schemas/`, `scripts/` and `src/`.

The five input roles use `<output>/roles/<role>/...`. The two completion roles
use `<output>/completion/roles/<role>/...`. Completion-role `source_path`
files may be absent during `--phase inputs`, because fresh model runs have not
happened yet; they must exist during `--phase complete`.

## Generated-value placeholders

Build-spec authors do not write hashes or repeat package identity. Templates
use exact one-key placeholder objects:

| Placeholder | Result |
|---|---|
| `{"$file_sha256": "data/..."}` | Hash of an already rendered declared support output |
| `{"$envelope_sha256": "evaluator"}` | Hash of a direct dependency envelope |
| `{"$role_dependencies": "reference_bundle"}` | Exact role dependency-hash map |
| `{"$identity": "scenario_id"}` | A verified package identity value |
| `{"$bound_json_field": {"path": "data/...", "field": "final_evidence"}}` | A field copied from an already rendered, hash-bound support JSON |
| `{"$formal_input_lock_sha256": true}` | The published pre-provider lock hash; completion roles only |
| `{"$formal_input_lock_verification": "variant-id"}` | The full result of re-running the provider-gate verifier for that variant; completion roles only |

For example:

```json
{
  "boundary_state_path": "data/formal/.../boundary-a.json",
  "boundary_state_sha256": {
    "$file_sha256": "data/formal/.../boundary-a.json"
  }
}
```

Any caller-supplied value whose field name ends in `_sha256` is rejected.
Support files are rendered in list order. A template may refer only to files
already rendered in its own role or a declared dependency, and to direct
predecessor envelopes. Domain evidence containing observed digest fields must
be selected from an already hash-bound source with `$bound_json_field`; this
keeps the anti-forgery rule intact.

Every `boundary_bundle` variant binds two different artifacts:

- `failure_surface_path` / `failure_surface_sha256`: the normalized formal
  wrapper containing `phase`, `operation` and `surface_result`;
- `raw_failure_report_path` / `raw_failure_report_sha256`: the exact native
  boundary/failure report supplied to the model runner.

They must not be conflated. The pre-provider verifier compares the actual
native report against `raw_failure_report_sha256` while independently
validating the normalized wrapper.

`reset_evidence` contains exactly one `prefix_path` / `prefix_sha256` pair.
Every variant reset capture must bind that same hash. The provider gate hashes
the actual prefix file passed to the runner and rejects the run before the
first model call if it differs from this bound copy.

Every raw-run declaration, its bound run-record JSON, and the
execution-control primary payload must also include
`"formal_input_lock_sha256": {"$formal_input_lock_sha256": true}`. Completion
is rejected unless all three resolve to the exact phase-one lock hash. A run
declaration additionally binds the unabridged native trajectory through
`raw_trajectory_path` / `raw_trajectory_sha256`. The trajectory must carry the
exact scenario, instance, variant, run ID, execution-control flag,
deterministic evaluation, and full
`$formal_input_lock_verification` object. A generated wrapper or summary is
not accepted as a substitute for the raw trajectory.

The reference role also binds a separately persisted
`reference_start_state`, and every run binds a separately persisted
`pre_model_boundary_evidence` file. Both must be byte-identical to the
admitted boundary state. The run declaration, run wrapper and raw trajectory
must agree on the pre-model file hash and variant. This prevents a passing
terminal state or a post-run recapture from being relabeled as the state that
was actually visible before provider access.

## Phase outputs

After `--phase inputs`:

```text
formal-input-lock.json
roles/{tool_contract,evaluator,reset_evidence,boundary_bundle,reference_bundle}/...
```

`formal-input-lock.json` contains only verified identity, producer commit,
scenario hash and the five input-envelope declarations. It contains neither
`raw_run_archive` nor `execution_control`. Its SHA-256 is therefore a causal
precondition for fresh model execution. Its exact public schema is
`schemas/formal-input-lock-v1.schema.json`.

After `--phase complete`, every input byte remains unchanged and one atomically
published subtree is added:

```text
completion/
  roles/{raw_run_archive,execution_control}/...
  declarations.json
```

`completion/declarations.json` contains all seven verified
`formal_evidence` declarations, matching `control_evidence`, and the exact
input-lock hash. Its two-phase path contract is published as
`schemas/formal-evidence-declarations-v1.schema.json`; role payload fields,
including raw-failure and lock-hash bindings, are covered by
`schemas/formal-evidence-payload-v1.schema.json`.

A `release_slot` must bind the path and SHA-256 of this declarations manifest
in `formal_evidence_declarations`; seven standalone envelope declarations are
insufficient. Promotion reloads the manifest, input lock and every raw
trajectory, then rechecks the complete chain. For a trusted family, it also
re-runs the registered pure evaluator over every reference terminal state and
raw control trajectory using the hash-bound prefix. Stored `passed`,
`components`, `checks` or `diagnostics` fields are evidence to verify, not
ground truth. Unknown evaluator families fail formal promotion.

## Pre-provider verification API

The model runner can verify one variant without reading completion evidence:

```python
verification = verify_formal_input_lock(
    "data/formal/.../formal-input-lock.json",
    root=repository_root,
    scenario_id="...",
    domain_id="forgejo",
    family_id="...",
    instance_id="public-dev-001",
    variant_id="...",
    failure_report_path="data/raw/...-boundary.json",
    prefix_path="data/scenarios/.../artifacts/prefix.json",
)
```

It returns:

- the exact input-lock SHA-256;
- all five input-envelope hashes;
- the selected variant's boundary-state hash;
- the selected variant's exact raw failure-report hash.
- the exact model-visible prefix hash.

Identity, current producer commit, scenario bytes, every envelope/payload
file, the dependency graph, selected raw report and actual runner prefix are
verified before a result is returned. The verifier never reads the two
completion roles.
