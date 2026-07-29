from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.forgejo_api import ForgejoAPI

OWNER = "aftermath"
REPOSITORY = "runtime-reset-smoke"
BASELINE_ISSUE = "snapshot baseline"
MUTATION_ISSUE = "post-snapshot mutation"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON object in {path}")
    return value


def _issue_titles(client: ForgejoAPI) -> list[str]:
    return sorted(
        str(item["title"])
        for item in client.list_issues(OWNER, REPOSITORY)
    )


def execute_phase(client: ForgejoAPI, phase: str) -> dict[str, Any]:
    if phase == "seed":
        repository = client.create_repository(REPOSITORY)
        issue = client.create_issue(
            OWNER,
            REPOSITORY,
            title=BASELINE_ISSUE,
            body="This record must survive a deterministic reset.",
        )
        titles = _issue_titles(client)
        passed = (
            repository.get("name") == REPOSITORY
            and issue.get("title") == BASELINE_ISSUE
            and titles == [BASELINE_ISSUE]
        )
    elif phase == "mutate":
        issue = client.create_issue(
            OWNER,
            REPOSITORY,
            title=MUTATION_ISSUE,
            body="This record must disappear after snapshot restoration.",
        )
        titles = _issue_titles(client)
        passed = (
            issue.get("title") == MUTATION_ISSUE
            and titles == [MUTATION_ISSUE, BASELINE_ISSUE]
        )
    elif phase == "verify-restored":
        titles = _issue_titles(client)
        passed = titles == [BASELINE_ISSUE]
    else:
        raise ValueError(f"unsupported validation phase: {phase}")
    return {
        "schema_version": "0.1",
        "phase": phase,
        "repository": f"{OWNER}/{REPOSITORY}",
        "issue_titles": titles,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exercise Forgejo's deterministic native reset."
    )
    parser.add_argument(
        "phase",
        choices=("seed", "mutate", "verify-restored"),
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credentials = _load(args.credentials)
    report = execute_phase(
        ForgejoAPI(
            base_url=str(credentials["base_url"]),
            token=str(credentials["token"]),
        ),
        args.phase,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
