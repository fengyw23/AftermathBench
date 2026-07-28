# ERPNext v15 runtime

This directory contains the source-built runtime definition and control plane
for the first native AftermathBench enterprise task. Component tests pass, but
the task is intentionally not execution-admitted until a container run has
replayed all four faults and terminal checks.

Pinned upstream revisions:

- ERPNext `b9c9b76f5b043bd542b01dd4fefe913416a7bb53`
- Frappe `c1afa13e12834dcdc1d82c4ba8bb3e5652163656`
- Frappe Docker `412de117d95b4a7f939993b70838c9d9463fa0cf`
- Toxiproxy `v2.12.0`

The benchmark will call only Frappe's public REST/document methods. ERPNext
remains responsible for validation, document submission, stock ledger,
general-ledger, outstanding-balance, and cancellation semantics.

The image build is also source-pinned. To inspect the exact fetch and build
commands:

```bash
export PYTHONPATH=src
python scripts/build_erpnext_runtime.py
```

On a host with Docker Engine 23+ or Podman:

```bash
python scripts/build_erpnext_runtime.py --execute
```

This uses the official open `frappe_docker` production Containerfile, applies
the checked-in patch that pins its Python base image by digest, and
builds Frappe `v15.116.0` and ERPNext `v15.118.1` from their public tags. The
expected commits are recorded in `runtime.lock.json`.

## Required services

- MariaDB;
- Redis cache and queue;
- Frappe web process;
- short and long workers;
- a benchmark-owned idempotent remittance receiver;
- a transparent, audited HTTP failure gateway;
- Toxiproxy on the Redis queue boundary.

## Valid fault boundaries

1. suppress the request before it reaches Frappe;
2. drop the response after the SQL transaction commits;
3. make the native `after_commit` webhook enqueue fail;
4. accept the queue job but pause its worker.

Injecting an artificial partial commit inside ERPNext's payment SQL transaction
is forbidden. Runtime admission requires replayed evidence for every advertised
variant.

## Native replay sequence

On a Docker host:

```bash
export PYTHONPATH=src
python scripts/build_erpnext_runtime.py --execute
python scripts/manage_erpnext_stack.py up
python scripts/manage_erpnext_stack.py setup
python scripts/build_erpnext_prefix.py \
  --credentials runtimes/erpnext/.runtime/credentials.json \
  --output runtimes/erpnext/.runtime/prefix.json
python scripts/manage_erpnext_stack.py snapshot \
  --snapshot runtimes/erpnext/.runtime/prefix.sql
```

Then run each hidden boundary:

```bash
python scripts/run_erpnext_failure.py \
  --variant request_not_reached \
  --credentials runtimes/erpnext/.runtime/credentials.json \
  --prefix runtimes/erpnext/.runtime/prefix.json \
  --snapshot runtimes/erpnext/.runtime/prefix.sql \
  --output runtimes/erpnext/.runtime/request_not_reached.json
```

The failure runner refuses to emit a report unless the database, invoice,
payment, queue, remittance, and gateway evidence match the requested variant.
The manual GitHub workflow `erpnext-native-runtime` performs the complete
source build and all four replays.
