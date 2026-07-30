from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.native_freeze import verify_frozen_bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recompute a frozen native bundle before provider access."
    )
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--private-attestation", type=Path, required=True)
    parser.add_argument("--public-commitment", type=Path, required=True)
    parser.add_argument(
        "--allow-unbound",
        action="append",
        default=[],
    )
    args = parser.parse_args()
    result = verify_frozen_bundle(
        bundle_root=args.bundle_root,
        private_attestation_path=args.private_attestation,
        public_commitment_path=args.public_commitment,
        allowed_unbound_relative_paths=args.allow_unbound,
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
