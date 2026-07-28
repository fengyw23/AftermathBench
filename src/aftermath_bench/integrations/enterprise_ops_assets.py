from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import urllib.request
import zipfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

ENTERPRISEOPS_REVISION = "de22905d21a080b83bf4a54258afe4250ee2dd55"
ENTERPRISEOPS_ARCHIVE_SHA256 = (
    "d947543d4fba1aabc4aade73d3df955114187b7a94da7ac825c4c31169ddab47"
)
ENTERPRISEOPS_ARCHIVE_URL = (
    "https://raw.githubusercontent.com/ServiceNow/EnterpriseOps-Gym/"
    f"{ENTERPRISEOPS_REVISION}/gym_dbs.zip"
)
ITSM_SEED_ENTRY = (
    "Domain Wise DBs and Task-DB Mappings/itsm/dbs/"
    "db_1765301900121_3mwjj54xy.sql"
)
ITSM_SEED_SHA256 = (
    "99f193904ef9c1f06c3ecff48000697653f178d6300c70e86d34d5a17081e3a4"
)

_INSERT_HEADER = re.compile(
    r"INSERT\s+INTO\s+([`\"\[]?[A-Za-z_][\w]*[`\"\]]?)"
    r"\s*\((.*?)\)\s*VALUES",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class SeedMaterialization:
    database_path: Path
    source_entry: str
    source_sha256: str
    table_count: int
    row_count: int
    table_rows: dict[str, int]


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def default_cache_dir() -> Path:
    configured = os.environ.get("AFTERMATH_CACHE_DIR")
    if configured:
        return Path(configured)
    return Path.home() / ".cache" / "aftermath-bench"


def fetch_enterpriseops_archive(
    destination: str | Path | None = None,
    *,
    url: str = ENTERPRISEOPS_ARCHIVE_URL,
) -> Path:
    target = (
        Path(destination)
        if destination is not None
        else default_cache_dir() / "enterpriseops" / ENTERPRISEOPS_REVISION / "gym_dbs.zip"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256_file(target) == ENTERPRISEOPS_ARCHIVE_SHA256:
            return target
        raise ValueError(f"existing archive has the wrong SHA-256: {target}")

    temporary = target.with_suffix(".download")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AftermathBench asset fetcher"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with temporary.open("wb") as handle:
                while block := response.read(1024 * 1024):
                    handle.write(block)
        observed = sha256_file(temporary)
        if observed != ENTERPRISEOPS_ARCHIVE_SHA256:
            raise ValueError(
                "downloaded EnterpriseOps archive failed SHA-256 validation: "
                f"expected {ENTERPRISEOPS_ARCHIVE_SHA256}, observed {observed}"
            )
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def read_seed_sql(
    archive_path: str | Path,
    *,
    entry: str = ITSM_SEED_ENTRY,
    expected_sha256: str = ITSM_SEED_SHA256,
) -> str:
    archive = Path(archive_path)
    if sha256_file(archive) != ENTERPRISEOPS_ARCHIVE_SHA256:
        raise ValueError("EnterpriseOps archive SHA-256 does not match pinned revision")
    with zipfile.ZipFile(archive) as bundle:
        payload = bundle.read(entry)
    observed = hashlib.sha256(payload).hexdigest()
    if observed != expected_sha256:
        raise ValueError(
            f"seed SHA-256 mismatch: expected {expected_sha256}, observed {observed}"
        )
    return payload.decode("utf-8")


def infer_insert_schema(seed_sql: str) -> dict[str, tuple[str, ...]]:
    tables: dict[str, list[str]] = {}
    for match in _INSERT_HEADER.finditer(seed_sql):
        table = match.group(1).strip("`\"[]")
        columns = [
            column.strip().strip("`\"[]")
            for column in match.group(2).split(",")
        ]
        table_columns = tables.setdefault(table, [])
        for column in columns:
            if column not in table_columns:
                table_columns.append(column)
    if not tables:
        raise ValueError("seed contains no INSERT statements")
    return {
        table: tuple(columns)
        for table, columns in sorted(tables.items())
    }


def materialize_seed_sqlite(
    seed_sql: str,
    database_path: str | Path,
    *,
    source_entry: str = ITSM_SEED_ENTRY,
    source_sha256: str = ITSM_SEED_SHA256,
) -> SeedMaterialization:
    target = Path(database_path)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    schema = infer_insert_schema(seed_sql)
    with closing(sqlite3.connect(target)) as connection, connection:
        for table, columns in schema.items():
            quoted_columns = ", ".join(f'"{column}"' for column in columns)
            connection.execute(f'CREATE TABLE "{table}" ({quoted_columns})')
        connection.executescript(seed_sql)
        table_rows = {
            table: int(
                connection.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
            )
            for table in schema
        }
    return SeedMaterialization(
        database_path=target,
        source_entry=source_entry,
        source_sha256=source_sha256,
        table_count=len(schema),
        row_count=sum(table_rows.values()),
        table_rows=table_rows,
    )


def materialize_itsm_seed(
    archive_path: str | Path,
    database_path: str | Path,
) -> SeedMaterialization:
    seed_sql = read_seed_sql(archive_path)
    return materialize_seed_sqlite(seed_sql, database_path)
