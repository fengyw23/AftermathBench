# ERPNext v15 runtime

This directory will contain the reproducible, source-built runtime for the
first native AftermathBench enterprise task. It is intentionally not presented
as executable yet.

Pinned upstream revisions:

- ERPNext `b9c9b76f5b043bd542b01dd4fefe913416a7bb53`
- Frappe `c1afa13e12834dcdc1d82c4ba8bb3e5652163656`

The benchmark will call only Frappe's public REST/document methods. ERPNext
remains responsible for validation, document submission, stock ledger,
general-ledger, outstanding-balance, and cancellation semantics.

The image build is also source-pinned. To inspect the exact fetch and build
commands:

```bash
set PYTHONPATH=src
python scripts/build_erpnext_runtime.py
```

On a host with Docker Engine 23+ or Podman:

```bash
python scripts/build_erpnext_runtime.py --execute
```

This uses the official open `frappe_docker` production Containerfile, but
builds Frappe `v15.116.0` and ERPNext `v15.118.1` from their public tags. The
expected commits are recorded in `runtime.lock.json`.

## Required services

- MariaDB;
- Redis cache and queue;
- Frappe web process;
- short and long workers;
- scheduler;
- a benchmark-owned idempotent remittance receiver;
- a fault proxy on the HTTP and queue boundaries.

## Valid fault boundaries

1. suppress the request before it reaches Frappe;
2. drop the response after the SQL transaction commits;
3. make the native `after_commit` webhook enqueue fail;
4. accept the queue job but pause its worker.

Injecting an artificial partial commit inside ERPNext's payment SQL transaction
is forbidden. Runtime admission requires replayed evidence for every advertised
variant.
