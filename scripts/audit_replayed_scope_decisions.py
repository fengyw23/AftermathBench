from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.replay_scope_decision import audit_replayed_scope_decisions


def _read(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected object in {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit recovery-scope decision depth from native replays."
    )
    parser.add_argument("--boundary-audit", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--require-profile",
        action="store_true",
        help="Return nonzero when the replayed matrix misses its planned profile.",
    )
    args = parser.parse_args()
    result = audit_replayed_scope_decisions(
        boundary_audit=_read(args.boundary_audit),
        scenario=_read(args.scenario),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.require_profile and not result["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
