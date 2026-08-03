from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that frozen ERPNext API credentials survive restore."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8080",
    )
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
    try:
        response = FrappeHTTPAdapter(
            FrappeConfig(
                base_url=args.base_url,
                api_key=str(credentials["api_key"]),
                api_secret=str(credentials["api_secret"]),
            )
        ).get_resource("User", "Administrator")
        document = response.get("data")
        passed = isinstance(document, dict) and document.get("name") == "Administrator"
    except (OSError, RuntimeError, KeyError, json.JSONDecodeError):
        passed = False
    print(
        json.dumps(
            {
                "schema_version": "1.0",
                "passed": passed,
                "credential_values_published": False,
                "document_content_published": False,
            }
        )
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
