# Invalid execution-control run: CLI forwarding defect

GitHub Actions run `30398344331` requested `execution_control=true`, but the
`run-native-model` CLI did not forward `args.execution_control` to the native
runner. The archived trajectories therefore truthfully record
`"execution_control": false`, and their prompts contain no execution-control
condition.

This run is excluded from every execution-control result. It is retained as
an immutable audit artifact because it exposed an experiment-pipeline defect.
The defect is covered by
`tests/test_cli_native_model.py::NativeModelCLIForwardingTest`.

The trajectories contain no API credential or authorization header.
