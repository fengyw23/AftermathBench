# ERPNext sales-return execution control

GitHub Actions run
[`30518617941`](https://github.com/fengyw23/AftermathBench/actions/runs/30518617941)
executed `glm-5.2` on all four matched sales-return boundaries at commit
`9e2760a253c41351313f580de3c511cfac6125b3`.

This is an execution-only control. The model received the exact terminal
recovery scope but not the hidden boundary label. It still had to inspect the
current ERPNext documents, linked invoices, jobs and external delivery state,
then select and execute the state-appropriate public tools.

Results:

- Recovery Integrity: 4/4;
- matched-group success: 1/1;
- Goal Completion, Repair Completeness, Preservation and Protocol Safety:
  4/4 each;
- provider/runtime errors: 0;
- model tool errors: 0;
- scientific gate: 100% observed versus 80% required.

The complete model-visible input, tool calls, tool results, failure-boundary
reports and terminal evaluations are retained under `repetition-01/`.
`control.json` records file hashes and the independent trajectory audit.
No API credential is present in the archive.

This result establishes that the public tool surface can execute a supplied
correct scope. It does not measure whether the model can infer that scope; the
ordinary condition is evaluated separately.
