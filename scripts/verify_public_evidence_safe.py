from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

_SENSITIVE_FIELDS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "password",
        "secret",
        "token",
    }
)
_NATIVE_RESTORE_ARCHIVES = frozenset(
    {"forgejo-data.tar.gz", "webhook-sink-data.tar.gz"}
)
_FORBIDDEN_NAMES = frozenset({"credentials.json", ".env", *_NATIVE_RESTORE_ARCHIVES})
_FORBIDDEN_SUFFIXES = frozenset({".key", ".pem"})
_SCAN_CHUNK_BYTES = 1024 * 1024


def _contains_secret(path: Path, secrets: set[bytes]) -> bool:
    if not secrets:
        return False
    overlap = max(len(secret) for secret in secrets) - 1
    tail = b""
    with path.open("rb") as stream:
        while chunk := stream.read(_SCAN_CHUNK_BYTES):
            window = tail + chunk
            if any(secret in window for secret in secrets):
                return True
            tail = window[-overlap:] if overlap > 0 else b""
    return False


def _credential_values(value: Any, *, field: str = "") -> set[bytes]:
    if isinstance(value, dict):
        result: set[bytes] = set()
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            result.update(_credential_values(item, field=normalized))
        return result
    if isinstance(value, list):
        result = set()
        for item in value:
            result.update(_credential_values(item, field=field))
        return result
    if field in _SENSITIVE_FIELDS and isinstance(value, str) and len(value) >= 4:
        return {value.encode("utf-8")}
    return set()


def verify_public_evidence(
    roots: list[Path],
    *,
    credentials: list[Path],
    secret_environment_variables: list[str],
    allow_native_restore_archives: bool = False,
) -> dict[str, Any]:
    secrets: set[bytes] = set()
    for path in credentials:
        payload = json.loads(path.read_text(encoding="utf-8"))
        secrets.update(_credential_values(payload))
    for name in secret_environment_variables:
        value = os.environ.get(name)
        if not value:
            raise ValueError(f"secret environment variable is empty: {name}")
        secrets.add(value.encode("utf-8"))

    unsafe_names: list[str] = []
    secret_hits: list[str] = []
    scanned = 0
    skipped_native_restore_archives = 0
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"public evidence root is not a directory: {root}")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"public evidence must not contain symlinks: {path}")
            if not path.is_file():
                continue
            scanned += 1
            relative = f"{root.name}/{path.relative_to(root).as_posix()}"
            if (
                path.name in _FORBIDDEN_NAMES
                and not (
                    allow_native_restore_archives
                    and path.name in _NATIVE_RESTORE_ARCHIVES
                )
            ) or path.suffix.lower() in _FORBIDDEN_SUFFIXES:
                unsafe_names.append(relative)
            if path.name in _NATIVE_RESTORE_ARCHIVES:
                if allow_native_restore_archives:
                    skipped_native_restore_archives += 1
                continue
            if _contains_secret(path, secrets):
                secret_hits.append(relative)
    return {
        "passed": not unsafe_names and not secret_hits,
        "scanned_file_count": scanned,
        "credential_source_count": len(credentials),
        "environment_secret_count": len(secret_environment_variables),
        "skipped_native_restore_archive_count": (skipped_native_restore_archives),
        "unsafe_names": unsafe_names,
        "secret_hits": secret_hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reject credential-like files and exact secret values from a "
            "public evidence tree without printing any secret."
        )
    )
    parser.add_argument("--root", type=Path, action="append", required=True)
    parser.add_argument(
        "--credentials-json",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--secret-env",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--allow-native-restore-archives",
        action="store_true",
        help=(
            "Permit native restore archives only while scanning the private "
            "source tree before public packaging."
        ),
    )
    args = parser.parse_args()
    try:
        result = verify_public_evidence(
            [path.resolve() for path in args.root],
            credentials=[path.resolve(strict=True) for path in args.credentials_json],
            secret_environment_variables=args.secret_env,
            allow_native_restore_archives=args.allow_native_restore_archives,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"passed": False, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
