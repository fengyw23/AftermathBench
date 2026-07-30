from __future__ import annotations

import base64
import unittest
from typing import Any

from scripts.run_forgejo_publication_boundary import (
    _capture_release_and_assets,
)


class _FakeForgejoAPI:
    def __init__(self) -> None:
        self.uploaded: list[dict[str, Any]] = []
        self.release_reads = 0

    def list_releases(
        self,
        owner: str,
        repository: str,
    ) -> list[dict[str, Any]]:
        self.release_reads += 1
        return [
            {
                "id": 17,
                "tag_name": "v1.2.3",
                "target_commitish": "release/1.2",
                "assets": list(self.uploaded),
            }
        ]

    def get_repository_content(
        self,
        owner: str,
        repository: str,
        *,
        path: str,
        ref: str,
    ) -> dict[str, str]:
        return {
            "content": base64.b64encode(
                f"source:{path}".encode()
            ).decode()
        }

    def create_release_attachment(
        self,
        owner: str,
        repository: str,
        release_id: int,
        *,
        name: str,
        content: bytes,
    ) -> dict[str, Any]:
        asset = {
            "id": len(self.uploaded) + 1,
            "name": name,
            "size": len(content),
        }
        self.uploaded.append(asset)
        return asset

    def list_release_attachments(
        self,
        owner: str,
        repository: str,
        release_id: int,
    ) -> list[dict[str, Any]]:
        return list(self.uploaded)


class ForgejoPublicationBoundaryCaptureTests(unittest.TestCase):
    def test_release_is_refreshed_after_each_preloaded_asset_write(self) -> None:
        for role in ("binary", "checksum", "sbom"):
            with self.subTest(role=role):
                api = _FakeForgejoAPI()
                prefix = {
                    "owner": "sample-owner",
                    "repository": "sample-repository",
                    "release_tag": "v1.2.3",
                    "base_branch": "release/1.2",
                    "expected_assets": [
                        {
                            "role": role,
                            "name": f"artifact-{role}",
                            "source_path": f"release/{role}",
                        }
                    ],
                }

                release, assets = _capture_release_and_assets(
                    api,
                    prefix,
                    preloaded_asset_roles=(role,),
                )

                self.assertGreaterEqual(api.release_reads, 2)
                self.assertEqual(assets, api.uploaded)
                self.assertIsNotNone(release)
                assert release is not None
                self.assertEqual(release["assets"], assets)

    def test_missing_release_is_preserved_as_absent(self) -> None:
        class _MissingReleaseAPI(_FakeForgejoAPI):
            def list_releases(
                self,
                owner: str,
                repository: str,
            ) -> list[dict[str, Any]]:
                self.release_reads += 1
                return []

        api = _MissingReleaseAPI()
        release, assets = _capture_release_and_assets(
            api,
            {
                "owner": "sample-owner",
                "repository": "sample-repository",
                "release_tag": "v1.2.3",
                "base_branch": "release/1.2",
                "expected_assets": [],
            },
            preloaded_asset_roles=(),
        )

        self.assertIsNone(release)
        self.assertEqual(assets, [])
        self.assertEqual(api.uploaded, [])


if __name__ == "__main__":
    unittest.main()
