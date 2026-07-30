from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.forgejo_publication_state_evidence import (
    ForgejoPublicationStateEvidenceError,
    capture_forgejo_publication_state_evidence,
    establish_expected_projection,
    write_state_evidence,
)
from aftermath_bench.integrations.forgejo_publication_faults import (
    FORGEJO_PUBLICATION_VARIANTS,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture deterministic native reset or failure-boundary state "
            "evidence for a Forgejo publication instance."
        )
    )
    parser.add_argument("--phase", choices=("reset", "boundary"), required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument(
        "--variant",
        choices=FORGEJO_PUBLICATION_VARIANTS,
        required=True,
    )
    parser.add_argument("--bundle-manifest", type=Path, required=True)
    parser.add_argument("--forgejo-archive", type=Path, required=True)
    parser.add_argument("--webhook-sink-archive", type=Path, required=True)
    projection_mode = parser.add_mutually_exclusive_group()
    projection_mode.add_argument("--expected-projection", type=Path)
    projection_mode.add_argument(
        "--establish-expected-projection",
        type=Path,
    )
    parser.add_argument("--reset-evidence", type=Path)
    parser.add_argument("--failure-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if (
            args.establish_expected_projection is not None
            and args.establish_expected_projection.resolve(strict=False)
            == args.output.resolve(strict=False)
        ):
            raise ForgejoPublicationStateEvidenceError(
                "established projection and evidence output must be distinct paths"
            )
        payload = capture_forgejo_publication_state_evidence(
            phase=args.phase,
            credentials_path=args.credentials,
            prefix_path=args.prefix,
            variant_id=args.variant,
            bundle_manifest_path=args.bundle_manifest,
            forgejo_archive_path=args.forgejo_archive,
            webhook_sink_archive_path=args.webhook_sink_archive,
            expected_projection_path=args.expected_projection,
            establish_expected_projection=(
                args.establish_expected_projection is not None
            ),
            reset_evidence_path=args.reset_evidence,
            failure_report_path=args.failure_report,
        )
        if args.establish_expected_projection is not None:
            payload = establish_expected_projection(
                args.establish_expected_projection,
                payload,
            )
        write_state_evidence(args.output, payload)
    except ForgejoPublicationStateEvidenceError as error:
        print(
            json.dumps(
                {
                    "passed": False,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 2
    verified = (
        payload["reset_verified"]
        if args.phase == "reset"
        else payload["boundary_validation_passed"]
    )
    established = bool(
        payload.get("expected_projection_establishment", {}).get("performed")
    )
    print(
        json.dumps(
            {
                "passed": bool(verified or established),
                "scenario_id": payload["scenario_id"],
                "variant_id": payload["variant_id"],
                "phase": payload["phase"],
                "reset_verified": payload.get("reset_verified"),
                "expected_projection_established": established,
                "state_fingerprint": payload["state_fingerprint"],
                "bundle_manifest_file_sha256": payload["bundle_manifest_file_sha256"],
            },
            ensure_ascii=False,
        )
    )
    if (
        args.phase == "reset"
        and not payload["reset_verified"]
        and args.establish_expected_projection is None
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
