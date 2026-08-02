from __future__ import annotations

import argparse
import tarfile
from pathlib import Path, PurePosixPath


def _validate_member(member: tarfile.TarInfo) -> None:
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe archive member: {member.name!r}")
    if not path.parts or path.parts[0] != "private":
        raise ValueError(f"archive member is outside private/: {member.name!r}")
    if member.issym() or member.islnk() or member.isdev() or member.isfifo():
        raise ValueError(f"unsupported archive member: {member.name!r}")
    if not (member.isfile() or member.isdir()):
        raise ValueError(f"unsupported archive member type: {member.name!r}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely extract a decrypted hidden native bundle."
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    if any(args.destination.iterdir()):
        raise ValueError("hidden bundle destination must be empty")
    with tarfile.open(args.archive, "r:gz") as archive:
        members = archive.getmembers()
        if not members:
            raise ValueError("hidden bundle archive is empty")
        for member in members:
            _validate_member(member)
        archive.extractall(args.destination, members=members, filter="data")
    private = args.destination / "private"
    if not private.is_dir():
        raise ValueError("hidden bundle archive did not contain private/")
    print(f"extracted {len(members)} safe archive members")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
