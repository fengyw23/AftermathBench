from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.verify_public_evidence_safe import (
    _SCAN_CHUNK_BYTES,
    verify_public_evidence,
)


class PublicEvidenceSafetyTests(unittest.TestCase):
    def test_accepts_public_files_and_ignores_non_secret_identity_fields(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "report.json").write_text(
                '{"username":"owner","base_url":"http://example.invalid"}',
                encoding="utf-8",
            )
            credentials = root / "private.json"
            credentials.write_text(
                json.dumps(
                    {
                        "username": "owner",
                        "base_url": "http://example.invalid",
                        "token": "private-token",
                        "password": "private-password",
                    }
                ),
                encoding="utf-8",
            )

            result = verify_public_evidence(
                [evidence],
                credentials=[credentials],
                secret_environment_variables=[],
            )

        self.assertTrue(result["passed"])
        self.assertEqual(result["scanned_file_count"], 1)

    def test_rejects_exact_file_or_environment_secret_without_exposing_it(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "trajectory.json").write_text(
                '{"debug":"provider-secret"}',
                encoding="utf-8",
            )
            credentials = root / "private.json"
            credentials.write_text(
                '{"token":"forgejo-secret"}',
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"PROVIDER_SECRET": "provider-secret"},
            ):
                result = verify_public_evidence(
                    [evidence],
                    credentials=[credentials],
                    secret_environment_variables=["PROVIDER_SECRET"],
                )

        self.assertFalse(result["passed"])
        self.assertEqual(result["secret_hits"], ["evidence/trajectory.json"])
        self.assertNotIn("provider-secret", json.dumps(result))
        self.assertNotIn("forgejo-secret", json.dumps(result))

    def test_rejects_credential_and_private_key_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "credentials.json").write_text("{}", encoding="utf-8")
            (root / "signing.pem").write_text("public", encoding="utf-8")

            result = verify_public_evidence(
                [root],
                credentials=[],
                secret_environment_variables=[],
            )

        self.assertFalse(result["passed"])
        self.assertEqual(
            result["unsafe_names"],
            [f"{root.name}/credentials.json", f"{root.name}/signing.pem"],
        )

    def test_native_restore_archives_are_publicly_forbidden_by_default(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "forgejo-data.tar.gz").write_bytes(b"private")
            (root / "webhook-sink-data.tar.gz").write_bytes(b"private")

            public = verify_public_evidence(
                [root],
                credentials=[],
                secret_environment_variables=[],
            )
            private_source = verify_public_evidence(
                [root],
                credentials=[],
                secret_environment_variables=[],
                allow_native_restore_archives=True,
            )

        self.assertFalse(public["passed"])
        self.assertEqual(len(public["unsafe_names"]), 2)
        self.assertTrue(private_source["passed"])
        self.assertEqual(
            private_source["skipped_native_restore_archive_count"],
            2,
        )

    def test_streaming_scan_detects_a_secret_across_chunk_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = "boundary-secret-value"
            (root / "large.log").write_bytes(
                b"x" * (_SCAN_CHUNK_BYTES - 4) + secret.encode("utf-8")
            )
            with patch.dict(os.environ, {"STREAM_SECRET": secret}):
                result = verify_public_evidence(
                    [root],
                    credentials=[],
                    secret_environment_variables=["STREAM_SECRET"],
                )

        self.assertFalse(result["passed"])
        self.assertEqual(result["secret_hits"], [f"{root.name}/large.log"])


if __name__ == "__main__":
    unittest.main()
