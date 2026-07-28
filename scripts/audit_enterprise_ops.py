#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path

INSERT_PATTERN = re.compile(
    r'INSERT\s+INTO\s+[`"]?([A-Za-z_][\w]*)[`"]?\s*\(([^)]*)\)',
    re.IGNORECASE | re.DOTALL,
)


def audit_seed_archive(path: Path) -> dict:
    domains: dict[str, dict] = defaultdict(
        lambda: {"files": [], "union_tables": set(), "columns": defaultdict(set)}
    )
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.endswith(".sql"):
                continue
            parts = name.split("/")
            if len(parts) < 4:
                continue
            domain = parts[1]
            text = archive.read(name).decode("utf-8", errors="replace")
            file_tables: set[str] = set()
            for match in INSERT_PATTERN.finditer(text):
                table = match.group(1)
                columns = {
                    item.strip().strip('`"')
                    for item in match.group(2).split(",")
                }
                file_tables.add(table)
                domains[domain]["union_tables"].add(table)
                domains[domain]["columns"][table].update(columns)
            domains[domain]["files"].append(
                {
                    "path": name,
                    "bytes": len(text.encode("utf-8")),
                    "tables_in_seed_inserts": len(file_tables),
                }
            )

    result = {"archive": str(path), "domains": {}}
    for domain, data in sorted(domains.items()):
        file_counts = [
            item["tables_in_seed_inserts"]
            for item in data["files"]
        ]
        result["domains"][domain] = {
            "sql_file_count": len(data["files"]),
            "union_table_count": len(data["union_tables"]),
            "max_tables_in_one_snapshot": max(file_counts, default=0),
            "min_tables_in_one_snapshot": min(file_counts, default=0),
            "tables": sorted(data["union_tables"]),
            "files": sorted(data["files"], key=lambda item: item["path"]),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_seed_archive(args.archive)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

