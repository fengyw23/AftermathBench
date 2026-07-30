# ERPNext sales-return historical native evidence

This directory is a byte-for-byte archive of the scientifically relevant JSON
that was missing from the repository but remained available in GitHub Actions
artifact `8714029126` (`erpnext-sales-return-prefix-30425865276`).

The archive intentionally contains only:

- the native prefix validation report;
- one raw post-error boundary for each of the four matched variants; and
- one deterministic reference-recovery report for each variant.

The 56 raw fixed-policy reports were not copied because the repository already
preserves their admission-relevant aggregate result in the scenario's
`baselines.json`. Seven other JSON files were exact SHA-256 duplicates of
files already checked in. Compose logs, status dumps, archives, and credentials
are not included.

## What this archive does and does not establish

These files are useful historical evidence that the four variants reached
different native ERPNext states behind the same visible failure and that each
state had a successful deterministic recovery. `provenance.json` binds every
file to its original artifact path, byte length, and SHA-256.

They are **not formal benchmark evidence**. They use the legacy `0.1` report
shape, do not include a per-variant reset snapshot, do not declare the current
formal evidence dependency roles, and are not cross-bound to a current formal
scenario bundle. Consequently:

- `historical_only` is `true`;
- `formal_evidence` is `false`;
- `current_gate_compatible` is `false`; and
- this archive must not be used to admit ERPNext into a formal release.

The current release exclusion therefore remains correct. New formal evidence
must be produced by the current builder and runtime gate, not promoted from
this archive.

## Integrity check

Run the dedicated repository test:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p "test_erpnext_historical_evidence_archive.py"
```

The test validates provenance identity, file hashes and sizes, legacy schema
status, reference linkage, and the non-formal-use declaration without relying
on the downloaded artifact.
