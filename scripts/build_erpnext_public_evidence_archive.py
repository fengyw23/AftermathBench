from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from aftermath_bench.evidence_manifest import build_file_manifest

_BUNDLE_FILES = (
    "database.sql",
    "redis-queue.tar",
    "gateway-audit.tar",
    "remittance-audit.tar",
)
_UNSAFE_NAMES = frozenset({"credentials.json", ".env"})
_UNSAFE_SUFFIXES = frozenset({".key", ".pem"})


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_bundle(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "1.0"
        or payload.get("capture_mode")
        != "simultaneous_service_quiescence"
        or not isinstance(payload.get("files"), dict)
    ):
        raise ValueError(f"invalid ERPNext bundle manifest: {path}")
    return payload


def build_public_archive(
    source_root: Path,
    output_root: Path,
    *,
    expected_restore_bundle_count: int,
) -> dict[str, Any]:
    source = source_root.resolve(strict=True)
    output = output_root.resolve(strict=False)
    if not source.is_dir():
        raise ValueError("source root must be a directory")
    if output.exists():
        raise ValueError("public output root already exists")
    if expected_restore_bundle_count < 1:
        raise ValueError(
            "expected restore bundle count must be positive"
        )
    if (
        output == source
        or source in output.parents
        or output in source.parents
    ):
        raise ValueError(
            "source and public output roots must not overlap"
        )
    source_entries = sorted(source.rglob("*"))
    symlinks = [path for path in source_entries if path.is_symlink()]
    if symlinks:
        raise ValueError(f"source contains a symlink: {symlinks[0]}")
    bundle_manifests = [
        path
        for path in source_entries
        if path.is_file() and path.name == "bundle.json"
    ]
    if len(bundle_manifests) != expected_restore_bundle_count:
        raise ValueError(
            "native restore bundle count mismatch: "
            f"expected={expected_restore_bundle_count}, "
            f"observed={len(bundle_manifests)}"
        )
    archive_paths: set[Path] = set()
    omissions: list[dict[str, Any]] = []
    for manifest_path in bundle_manifests:
        manifest = _load_bundle(manifest_path)
        manifest_relative = manifest_path.relative_to(source).as_posix()
        declarations = manifest["files"]
        declared_names = {
            str(item.get("path"))
            for item in declarations.values()
            if isinstance(item, dict)
        }
        if declared_names != set(_BUNDLE_FILES):
            raise ValueError(
                f"ERPNext bundle files are not exact: {manifest_path}"
            )
        for declaration in declarations.values():
            name = str(declaration["path"])
            archive = manifest_path.parent / name
            if not archive.is_file() or archive.is_symlink():
                raise ValueError(
                    f"native restore file is missing or unsafe: {archive}"
                )
            observed_sha256 = _sha256_file(archive)
            if (
                archive.stat().st_size != declaration.get("bytes")
                or observed_sha256 != declaration.get("sha256")
            ):
                raise ValueError(
                    f"native restore file hash drifted: {archive}"
                )
            archive_paths.add(archive.resolve())
            omissions.append(
                {
                    "path": archive.relative_to(source).as_posix(),
                    "bytes": archive.stat().st_size,
                    "sha256": observed_sha256,
                    "bundle_manifest_path": manifest_relative,
                    "reason": "contains_native_runtime_secrets_or_state",
                }
            )
    discovered_archives = {
        path.resolve()
        for path in source_entries
        if path.is_file() and path.name in _BUNDLE_FILES
    }
    if discovered_archives != archive_paths:
        raise ValueError(
            "every native restore file must belong to a declared bundle"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = Path(
        tempfile.mkdtemp(
            prefix=".erpnext-public-evidence-",
            dir=output.parent,
        )
    )
    try:
        assert temporary is not None
        for path in source_entries:
            if not path.is_file() or path.resolve() in archive_paths:
                continue
            if (
                path.name in _UNSAFE_NAMES
                or path.suffix.lower() in _UNSAFE_SUFFIXES
            ):
                raise ValueError(
                    f"credential-like file cannot enter public staging: {path}"
                )
            destination = temporary / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        omission_payload = {
            "schema_version": "1.0",
            "artifact_type": "public_evidence_omission_manifest",
            "source_tree": source.name,
            "restore_bundle_count": len(bundle_manifests),
            "omitted_file_count": len(omissions),
            "omissions": omissions,
        }
        (temporary / "omissions.json").write_text(
            json.dumps(
                omission_payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        files = build_file_manifest(
            temporary,
            exclude={"files.json"},
        )
        (temporary / "files.json").write_text(
            json.dumps(files, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary)
    return {
        "passed": True,
        "output_root": str(output),
        "restore_bundle_count": len(bundle_manifests),
        "omitted_file_count": len(omissions),
        "public_file_count": files["file_count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a public ERPNext evidence tree while replacing exact "
            "native restore state with hash/size omission declarations."
        )
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--expected-restore-bundle-count",
        type=int,
        required=True,
    )
    args = parser.parse_args()
    try:
        result = build_public_archive(
            args.source_root,
            args.output_root,
            expected_restore_bundle_count=(
                args.expected_restore_bundle_count
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"passed": False, "error": str(error)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
