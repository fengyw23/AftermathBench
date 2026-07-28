# Task Schema

Each task specification is JSON and contains:

```text
schema_version
task_id
domain
title
user_instruction
systems
surface_failure
prefix_trace
protected_effects
entities
relations
nonlinear_motifs
required_evidence_sources
unsafe_retry_actions
variants
```

Each relation has a `source`, `target`, and semantic `type`. Relations are
directed for dependency-depth analysis.

Each failure variant records:

- its hidden commit-state class;
- a snapshot selector;
- a reference minimum mutation count used only for admission validation.

The hidden class and reference plan are never included in model input.

Snapshots must be constructed by replaying public write tools. A future
snapshot manifest will store the replay trace, state fingerprint, event-log
fingerprint, and base-environment revision.

