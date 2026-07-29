# Directional hardness

## Problem discovered

`k8s-settlement-orchestrated-dev-002` passes a strict structural admission:
four partial states, four tool signatures, 23 replayed relations and no fixed
policy above 25%. GLM-5.2 nevertheless solves all four validly.

The reason is that tool-signature diversity is not decision diversity. Every
variant has the same semantic recovery direction:

> forward-complete all missing obligations while skipping completed effects.

One reference may use five writes and another eight, but both instantiate the
same policy.

## New admission dimension

Future top-level hard tasks declare
`minimum_semantic_recovery_directions`. Reference reports must label a direction
that is verified by the final-state delta, not merely authored text. The initial
vocabulary is:

- `forward_complete`: finish the interrupted change;
- `rollback_to_stable`: undo only the uncommitted candidate path;
- `compensate_external_effect`: preserve an irreversible effect and apply its
  explicit compensating operation;
- `repair_downstream_only`: keep the main operation and repair controller,
  ledger or notification closure;
- `preserve_and_verify`: make no semantic change because the operation and
  closure already succeeded.

A matched family intended as a directional hard task must expose at least three
directions and a fixed single-direction policy must fail the matched group.

The label alone is not gold. The builder must derive it from a normalized state
delta, for example:

- candidate removed and stable service preserved → `rollback_to_stable`;
- migrated schema retained and new deployment activated → `forward_complete`;
- external delivery retained plus reversal event created →
  `compensate_external_effect`;
- only an audit/controller record changed → `repair_downstream_only`;
- zero domain mutations and all checks pass → `preserve_and_verify`.

## Backward compatibility

Existing scenarios use the structural profile and therefore set no minimum.
Their historical admission remains reproducible. They must not be described as
directionally hard. New benchmark claims should use the directional profile and
report both structural and directional admission results.
