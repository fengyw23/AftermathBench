from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

_CLASSIFIERS = (
    ("provider_timeout", re.compile(r"timed out|TimeoutError", re.IGNORECASE)),
    (
        "provider_http_error",
        re.compile(r"model endpoint returned HTTP\s+\d+", re.IGNORECASE),
    ),
    (
        "provider_connection_error",
        re.compile(
            r"URLError|urlopen error|RemoteDisconnected|ConnectionReset|"
            r"Temporary failure|Name or service not known",
            re.IGNORECASE,
        ),
    ),
    (
        "provider_response_error",
        re.compile(
            r"JSONDecodeError|choices.*(?:missing|KeyError)|"
            r"tool_calls.*(?:invalid|KeyError)",
            re.IGNORECASE,
        ),
    ),
    (
        "hidden_lifecycle_error",
        re.compile(r"hidden evaluation|usage ledger|hidden-test", re.IGNORECASE),
    ),
    (
        "native_authentication_error",
        re.compile(
            r"(?:HTTP(?: Error| status)?\s*)?(?:401|403)\b|"
            r"Unauthorized|Forbidden",
            re.IGNORECASE,
        ),
    ),
    (
        "native_runtime_error",
        re.compile(r"Connection refused|Forgejo|webhook|receiver", re.IGNORECASE),
    ),
)


def classify(text: str) -> str:
    for name, pattern in _CLASSIFIERS:
        if pattern.search(text):
            return name
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Classify private model logs without publishing log text, paths, "
            "variant identities or task content."
        )
    )
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logs = sorted(args.run_directory.rglob("*-attempt-*.log"))
    counts: Counter[str] = Counter()
    exception_types: Counter[str] = Counter()
    nonempty = 0
    for path in logs:
        text = path.read_text(encoding="utf-8", errors="replace")
        nonempty += int(bool(text.strip()))
        counts[classify(text)] += 1
        observed_types = re.findall(
            r"(?m)^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception))\s*:",
            text,
        )
        if observed_types:
            exception_types[observed_types[-1].rsplit(".", 1)[-1]] += 1
    trajectories = [
        path
        for path in args.run_directory.rglob("*.json")
        if path.name != "summary.json" and path.stat().st_size > 0
    ]
    payload = {
        "schema_version": "1.0",
        "attempt_log_count": len(logs),
        "nonempty_attempt_log_count": nonempty,
        "trajectory_count": len(trajectories),
        "classification_counts": dict(sorted(counts.items())),
        "terminal_exception_type_counts": dict(
            sorted(exception_types.items())
        ),
        "raw_log_text_published": False,
        "variant_identities_published": False,
        "task_content_published": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
