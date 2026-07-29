from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.evidence_projection import projection_admission_report


FACT_GROUPS = {
    "native_commit_cluster": (
        "schema_epoch",
        "migration_job_complete",
        "migration_job_failed",
        "service_version",
    ),
    "external_preparation": ("preparation",),
    "external_publication": ("publication",),
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    boundaries = {}
    references = {}
    for path in sorted(args.runtime_directory.glob("*-boundary.json")):
        payload = _read(path)
        variant = str(payload["variant"])
        boundaries[variant] = payload["counterfactual_facts"]
    for path in sorted(args.runtime_directory.glob("*-reference.json")):
        payload = _read(path)
        references[str(payload["variant"])] = str(
            payload["semantic_recovery_direction"]
        )
    result = projection_admission_report(
        variant_facts=boundaries,
        variant_scopes=references,
        evidence_fact_groups=FACT_GROUPS,
    )
    result.update(
        {
            "source": "replayed Kubernetes failure boundaries and references",
            "runtime_directory": str(args.runtime_directory),
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["all_declared_groups_have_witnesses"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
