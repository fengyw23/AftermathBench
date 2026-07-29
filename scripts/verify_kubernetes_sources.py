from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

from aftermath_bench.schema import repository_root


def _hash_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind-source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = repository_root()
    audit = json.loads(
        (
            root
            / "data"
            / "runtimes"
            / "kubernetes-v1.34"
            / "source_audit.json"
        ).read_text(encoding="utf-8")
    )
    checks: list[dict[str, object]] = []
    for source in audit["sources"]:
        repository = source["repository"]
        revision = source["revision"]
        for item in source["audited_paths"]:
            relative = item["path"]
            if repository.endswith("/kind"):
                content = (args.kind_source / relative).read_bytes()
            else:
                url = (
                    "https://raw.githubusercontent.com/kubernetes/"
                    f"kubernetes/{revision}/{relative}"
                )
                with urlopen(url, timeout=30) as response:
                    content = response.read()
            actual = _hash_bytes(content)
            checks.append(
                {
                    "repository": repository,
                    "revision": revision,
                    "path": relative,
                    "expected_sha256": item["sha256"],
                    "actual_sha256": actual,
                    "passed": actual == item["sha256"],
                }
            )
    payload = {
        "runtime_id": audit["runtime_id"],
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise RuntimeError("Kubernetes source audit verification failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
