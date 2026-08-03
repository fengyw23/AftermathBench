from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from aftermath_bench.integrations.erpnext_native_instance import (
    ERPNextNativeInstanceSpec,
)


def _fixture_sha(payload: object) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reject an ERPNext hidden instance that duplicates public data."
    )
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument(
        "--public-scenarios-root",
        type=Path,
        default=Path("data/scenarios"),
    )
    args = parser.parse_args()
    instance = ERPNextNativeInstanceSpec.from_path(args.instance_spec)
    fixture_sha = _fixture_sha(instance.fixture)
    collisions: list[str] = []
    for path in sorted(args.public_scenarios_root.glob("*/scenario.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("family") != instance.family:
            continue
        if payload.get("scenario_id") == instance.scenario_id:
            collisions.append(f"scenario_id:{path.as_posix()}")
        if _fixture_sha(payload.get("fixture")) == fixture_sha:
            collisions.append(f"fixture:{path.as_posix()}")
    if collisions:
        raise RuntimeError(
            "private ERPNext instance duplicates public evidence: "
            + ", ".join(collisions)
        )
    print(
        json.dumps(
            {
                "scenario_id": instance.scenario_id,
                "family": instance.family,
                "instance_spec_sha256": instance.sha256,
                "public_collision_count": 0,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
