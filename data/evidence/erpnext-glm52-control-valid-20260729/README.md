# Valid GLM-5.2 explicit-scope execution control

GitHub Actions run `30399812129` executed the four development hidden states
with the correct recovery scope explicitly supplied. All four trajectories
record `"execution_control": true`, contain the control condition in the
model-visible input, and pass every deterministic evaluator component.

Results:

- completed trajectories: 4/4;
- Recovery Integrity Pass: 4/4 (100%);
- Matched-Group Success: 1/1 (100%);
- Goal Completion, Repair Completeness, Preservation, Protocol Safety: 100%;
- provider/runtime errors: 0;
- model turns: 5–8 of the allowed 15.

This is an execution control, not a benchmark result. It demonstrates that a
model given the correct repair scope can complete the same native ERPNext
workflows with the same public tools and turn budget. The main task remains
responsible for discovering the authoritative state and selecting that scope.

The trajectories contain no API credential or authorization header.
