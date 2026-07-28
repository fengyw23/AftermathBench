from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_freeze(
    *,
    freeze_path: Path,
    scenario_path: Path,
    prefix_path: Path,
) -> dict[str, str]:
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    observed = {
        "scenario_id": str(
            json.loads(
                scenario_path.read_text(encoding="utf-8")
            )["scenario_id"]
        ),
        "scenario_sha256": _sha256(scenario_path),
        "prefix_sha256": _sha256(prefix_path),
    }
    mismatches = {
        key: {
            "expected": freeze.get(key),
            "observed": value,
        }
        for key, value in observed.items()
        if freeze.get(key) != value
    }
    if mismatches:
        raise RuntimeError(
            "native holdout does not match its pre-model freeze: "
            f"{mismatches}"
        )
    return observed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a regenerated native prefix against its freeze."
    )
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    args = parser.parse_args()
    observed = verify_freeze(
        freeze_path=args.freeze,
        scenario_path=args.scenario,
        prefix_path=args.prefix,
    )
    print(json.dumps(observed, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
