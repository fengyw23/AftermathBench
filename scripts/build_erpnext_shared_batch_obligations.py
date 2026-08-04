from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.erpnext_shared_batch_obligations import (
    build_shared_batch_obligation_interactions,
)
from aftermath_bench.integrations.erpnext_shared_batch_scope import (
    SHARED_BATCH_RECOVERY_SIGNATURES,
)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build replay-derived shared-batch obligation interactions."
    )
    parser.add_argument("--boundary-directory", type=Path, required=True)
    parser.add_argument("--probe-directory", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    prefix = _read(args.prefix)
    failures = {
        variant: _read(args.boundary_directory / f"{variant}.json")
        for variant in SHARED_BATCH_RECOVERY_SIGNATURES
    }
    probes = {
        variant: _read(args.probe_directory / f"{variant}.json")
        for variant in SHARED_BATCH_RECOVERY_SIGNATURES
    }
    payload, audit = build_shared_batch_obligation_interactions(
        scenario_id=prefix["scenario_id"],
        prefix=prefix,
        failures=failures,
        probes=probes,
    )
    if (
        not audit.replay_bound
        or audit.gold_scope_count != 4
        or audit.cross_obligation_witness_count < 4
        or audit.repair_preservation_conflict_count < 4
        or audit.variants_with_repair_preservation_conflict != 4
    ):
        raise RuntimeError(f"shared-batch obligation admission failed: {audit}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
