from __future__ import annotations

import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.forgejo_publication_state_evidence import (
    ForgejoPublicationStateEvidenceError,
    enrich_snapshot_assets_from_bound_archive,
)
from aftermath_bench.integrations.forgejo_publication_recovery import (
    ForgejoPublicationEnvironment,
)

_UUID = "01234567-89ab-4def-8123-456789abcdef"
_CONTENT = b"approved release attachment"
_MEMBER = f"./gitea/attachments/0/1/{_UUID}"


def _snapshot(*, size: int = len(_CONTENT), uuid: str = _UUID) -> dict:
    return {
        "target_release_assets": [
            {
                "id": 8,
                "name": "release.tar.gz",
                "size": size,
                "uuid": uuid,
                "download_count": 0,
                "browser_download_url": (
                    f"http://forgejo.invalid/attachments/{uuid}"
                ),
            }
        ],
        "protected_release_assets": [],
    }


def _write_archive(
    path: Path,
    members: list[tuple[str, bytes | None, bytes]],
) -> tuple[str, int]:
    with tarfile.open(path, mode="w:gz") as archive:
        for name, content, member_type in members:
            member = tarfile.TarInfo(name)
            member.type = member_type
            if content is not None:
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            else:
                member.linkname = "../../../../outside"
                archive.addfile(member)
    raw = path.read_bytes()
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _enrich(
    archive: Path,
    snapshot: dict,
    *,
    sha256: str | None = None,
    size: int | None = None,
) -> dict:
    raw = archive.read_bytes()
    return enrich_snapshot_assets_from_bound_archive(
        snapshot,
        archive,
        archive_sha256=sha256 or hashlib.sha256(raw).hexdigest(),
        archive_size_bytes=len(raw) if size is None else size,
    )


class ForgejoArchiveAssetReaderTests(unittest.TestCase):
    def test_hashes_exact_regular_member_without_changing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "forgejo-data.tar.gz"
            _write_archive(
                archive,
                [(_MEMBER, _CONTENT, tarfile.REGTYPE)],
            )

            result = _enrich(archive, _snapshot())

            asset = result["target_release_assets"][0]
            self.assertEqual(
                asset["content_sha256"],
                hashlib.sha256(_CONTENT).hexdigest(),
            )
            self.assertEqual(asset["content_size"], len(_CONTENT))
            self.assertEqual(asset["download_count"], 0)

    def test_rejects_invalid_uuid_missing_duplicate_and_symlink(self) -> None:
        cases = {
            "invalid attachment UUID": (
                [(_MEMBER, _CONTENT, tarfile.REGTYPE)],
                _snapshot(uuid="../not-a-uuid"),
            ),
            "missing attachment": (
                [],
                _snapshot(),
            ),
            "duplicate attachment": (
                [
                    (_MEMBER, _CONTENT, tarfile.REGTYPE),
                    (_MEMBER, _CONTENT, tarfile.REGTYPE),
                ],
                _snapshot(),
            ),
            "not a regular file": (
                [(_MEMBER, None, tarfile.SYMTYPE)],
                _snapshot(),
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, (message, (members, snapshot)) in enumerate(
                cases.items()
            ):
                with self.subTest(case=message):
                    archive = root / f"case-{index}.tar.gz"
                    _write_archive(archive, members)
                    with self.assertRaisesRegex(
                        ForgejoPublicationStateEvidenceError,
                        message,
                    ):
                        _enrich(archive, snapshot)

    def test_rejects_unsafe_paths_size_mismatch_and_changed_binding(
        self,
    ) -> None:
        cases = {
            "unsafe member path": (
                [
                    (_MEMBER, _CONTENT, tarfile.REGTYPE),
                    ("../escape", b"escape", tarfile.REGTYPE),
                ],
                _snapshot(),
                None,
                None,
            ),
            "size does not match": (
                [(_MEMBER, _CONTENT, tarfile.REGTYPE)],
                _snapshot(size=len(_CONTENT) + 1),
                None,
                None,
            ),
            "changed after": (
                [(_MEMBER, _CONTENT, tarfile.REGTYPE)],
                _snapshot(),
                "f" * 64,
                None,
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, (
                message,
                (members, snapshot, sha256, size),
            ) in enumerate(cases.items()):
                with self.subTest(case=message):
                    archive = root / f"case-{index}.tar.gz"
                    _write_archive(archive, members)
                    with self.assertRaisesRegex(
                        ForgejoPublicationStateEvidenceError,
                        message,
                    ):
                        _enrich(
                            archive,
                            snapshot,
                            sha256=sha256,
                            size=size,
                        )


class _MetadataAPI:
    def __init__(self) -> None:
        self.download_count = 0

    def list_releases(self, _owner: str, _repository: str) -> list[dict]:
        return [
            {"id": 8, "tag_name": "v2"},
            {"id": 7, "tag_name": "v1"},
        ]

    def list_release_attachments(
        self,
        _owner: str,
        _repository: str,
        release_id: int,
    ) -> list[dict]:
        suffix = "target" if release_id == 8 else "protected"
        return [
            {
                "id": release_id,
                "name": suffix,
                "uuid": _UUID,
                "size": len(_CONTENT),
                "browser_download_url": (
                    f"http://forgejo.invalid/attachments/{_UUID}"
                ),
                "download_count": 0,
            }
        ]

    def download(self, _url: str) -> bytes:
        self.download_count += 1
        return _CONTENT

    def get_pull_request(
        self,
        _owner: str,
        _repository: str,
        index: int,
    ) -> dict:
        return {"index": index}

    def get(self, path: str) -> dict:
        return {"path": path}

    def get_milestone(
        self,
        _owner: str,
        _repository: str,
        milestone_id: int,
    ) -> dict:
        return {"id": milestone_id}

    def list_branch_protections(
        self,
        _owner: str,
        _repository: str,
    ) -> list[dict]:
        return []

    def list_hooks(
        self,
        _owner: str,
        _repository: str,
    ) -> list[dict]:
        return []


class _MetadataWeb:
    @staticmethod
    def webhook_history(
        _owner: str,
        _repository: str,
        _hook_id: int,
    ) -> list:
        return []


class ForgejoSnapshotModeTests(unittest.TestCase):
    @staticmethod
    def _prefix() -> dict:
        return {
            "owner": "owner",
            "repository": "repository",
            "release_tag": "v2",
            "protected_release_tag": "v1",
            "pull_request_index": 2,
            "linked_issue_index": 1,
            "milestone_id": 3,
            "base_branch": "release/2",
            "protected_pull_request_index": 4,
            "protected_issue_index": 5,
            "coordinator_hook_id": 6,
            "provenance_hook_id": 7,
        }

    def test_metadata_snapshot_does_not_download_but_ordinary_snapshot_does(
        self,
    ) -> None:
        api = _MetadataAPI()
        environment = ForgejoPublicationEnvironment(
            api=api,  # type: ignore[arg-type]
            web=_MetadataWeb(),  # type: ignore[arg-type]
            prefix=self._prefix(),
            json_getter=lambda _url: {"deliveries": []},
        )

        metadata = environment.snapshot_metadata()

        self.assertEqual(api.download_count, 0)
        self.assertNotIn(
            "content_sha256",
            metadata["target_release_assets"][0],
        )

        ordinary = environment.snapshot()

        self.assertEqual(api.download_count, 2)
        self.assertEqual(
            ordinary["target_release_assets"][0]["content_sha256"],
            hashlib.sha256(_CONTENT).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
