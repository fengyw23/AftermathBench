# Invalid final comparison: easy CLI regression

GitHub Actions run `30401034855` is excluded from every final aggregate.

The frozen holdout portion completed 20/20 trajectories with no runtime error
and produced a preliminary 45% Recovery Integrity Pass, but the easy portion
never reached the model. Every `run-erpnext-model` invocation raised:

```text
AttributeError: 'Namespace' object has no attribute 'execution_control'
```

The native execution-control wiring fix had incorrectly read the native-only
CLI field from the legacy easy command. The run therefore contains 40 valid
easy failure-boundary reports but zero easy model trajectories. Comparing its
holdout score against an absent easy control would violate the experiment
protocol, so the entire comparison is invalid.

The fix gives `run-erpnext-model` an explicit non-control condition and adds a
CLI regression test for both commands. The final workflow also now:

- counts missing expected trajectories as infrastructure errors;
- preserves per-attempt logs;
- waits 30 seconds before the one allowed retry.

This directory retains the complete sanitized artifact, including the 20
preliminary holdout trajectories, so the exclusion remains auditable. It
contains no API credential, authorization header, or database dump.
