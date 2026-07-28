# Invalid final comparison: easy-runner signature mismatch

GitHub Actions run `30406508136` at commit `a789797` is excluded from all
benchmark scores.

The easy branch reached the native failure snapshots, but all 20 model
invocations failed before contacting the provider:

```text
TypeError: run_live_erpnext_agent() got an unexpected keyword argument
'execution_control'
```

The native hard runner supports an explicit-scope execution-control condition;
the legacy easy runner intentionally does not. A previous CLI repair correctly
stopped reading a missing `args.execution_control` field but incorrectly passed
`execution_control=False` into the easy runner. The mocked regression test had
encoded that same invalid assumption.

The run was force-cancelled before spending another 20 holdout calls. It
contains no valid easy comparison and no model result used in the report.

The correction removes the native-only keyword from the easy call entirely.
The regression test now asserts that the keyword is absent, while a separate
test still proves that `--execution-control` reaches the native hard runner.

