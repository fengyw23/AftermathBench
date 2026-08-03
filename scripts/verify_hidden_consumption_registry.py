from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from aftermath_bench.schema import repository_root
from aftermath_bench.strict_json import load_json_strict


SHA256 = re.compile(r"^[0-9a-f]{64}$")
TERMINAL_DISPOSITIONS = {"consumed", "invalidated"}


def validate_registry(path: Path, *, root: Path) -> tuple[dict, ...]:
    payload = load_json_strict(path)
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "records"}
        or payload.get("schema_version") != "1.0"
        or not isinstance(payload.get("records"), list)
    ):
        raise ValueError("hidden evaluation registry has an invalid contract")
    records: list[dict] = []
    commitments: set[str] = set()
    freeze_runs: set[int] = set()
    evaluation_runs: set[int] = set()
    for index, item in enumerate(payload["records"]):
        if not isinstance(item, dict) or set(item) != {
            "scenario_id",
            "public_commitment_sha256",
            "freeze_run_id",
            "evaluation_run_id",
            "disposition",
            "evidence_path",
        }:
            raise ValueError(f"registry record {index} has an invalid contract")
        commitment = item["public_commitment_sha256"]
        freeze_run = item["freeze_run_id"]
        evaluation_run = item["evaluation_run_id"]
        evidence = root / str(item["evidence_path"])
        if (
            not item["scenario_id"]
            or not isinstance(commitment, str)
            or SHA256.fullmatch(commitment) is None
            or freeze_run is not None
            and (type(freeze_run) is not int or freeze_run < 1)
            or type(evaluation_run) is not int
            or evaluation_run < 1
            or item["disposition"] not in TERMINAL_DISPOSITIONS
            or not evidence.is_file()
        ):
            raise ValueError(f"registry record {index} is invalid")
        if commitment in commitments or evaluation_run in evaluation_runs:
            raise ValueError("hidden evaluation registry identities must be unique")
        if freeze_run is not None and freeze_run in freeze_runs:
            raise ValueError("hidden freeze run ids must be unique")
        commitments.add(commitment)
        evaluation_runs.add(evaluation_run)
        if freeze_run is not None:
            freeze_runs.add(freeze_run)
        records.append(item)
    return tuple(records)


def assert_unconsumed(
    records: tuple[dict, ...],
    *,
    public_commitment_sha256: str,
    freeze_run_id: int,
) -> None:
    matches = [
        record
        for record in records
        if record["public_commitment_sha256"] == public_commitment_sha256
        or record["freeze_run_id"] == freeze_run_id
    ]
    if matches:
        record = matches[0]
        raise RuntimeError(
            "hidden instance is terminal and must never be evaluated again: "
            f"{record['scenario_id']} ({record['disposition']})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refuse reuse of consumed or invalidated hidden instances."
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("data/hidden_evaluation_registry.json"),
    )
    parser.add_argument("--public-commitment-sha256", required=True)
    parser.add_argument("--freeze-run-id", type=int, required=True)
    args = parser.parse_args()
    root = repository_root()
    registry = args.registry if args.registry.is_absolute() else root / args.registry
    records = validate_registry(registry, root=root)
    assert_unconsumed(
        records,
        public_commitment_sha256=args.public_commitment_sha256,
        freeze_run_id=args.freeze_run_id,
    )
    print(
        json.dumps(
            {
                "registry": str(registry),
                "terminal_record_count": len(records),
                "candidate_unconsumed": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
