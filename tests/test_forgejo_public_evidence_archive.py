from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_forgejo_public_evidence_archive import (
    build_public_archive,
)


class ForgejoPublicEvidenceArchiveTests(unittest.TestCase):
    @staticmethod
    def _write_bundle(root: Path, name: str) -> None:
        bundle = root / "bundles" / name
        bundle.mkdir(parents=True)
        forgejo = bundle / "forgejo-data.tar.gz"
        sink = bundle / "webhook-sink-data.tar.gz"
        forgejo.write_bytes(f"forgejo-{name}-private".encode())
        sink.write_bytes(f"sink-{name}-private".encode())
        (bundle / "bundle.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "capture_mode": "simultaneous_service_quiescence",
                    "forgejo_sha256": hashlib.sha256(forgejo.read_bytes()).hexdigest(),
                    "webhook_sink_sha256": hashlib.sha256(
                        sink.read_bytes()
                    ).hexdigest(),
                }
            ),
            encoding="utf-8",
        )

    def test_omits_bound_restore_archives_and_preserves_public_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "report.json").write_text("{}", encoding="utf-8")
            self._write_bundle(source, "prefix")
            self._write_bundle(source, "boundary-a")
            output = root / "public"

            result = build_public_archive(
                source,
                output,
                expected_restore_bundle_count=2,
            )
            omissions = json.loads(
                (output / "omissions.json").read_text(encoding="utf-8")
            )
            public_manifest = json.loads(
                (output / "files.json").read_text(encoding="utf-8")
            )

            self.assertTrue(result["passed"])
            self.assertEqual(result["omitted_file_count"], 4)
            self.assertTrue((output / "report.json").is_file())
            self.assertTrue((output / "bundles" / "prefix" / "bundle.json").is_file())
            self.assertFalse(
                (output / "bundles" / "prefix" / "forgejo-data.tar.gz").exists()
            )
            self.assertEqual(omissions["restore_bundle_count"], 2)
            self.assertTrue(
                all(
                    item["reason"] == "contains_native_runtime_secrets"
                    for item in omissions["omissions"]
                )
            )
            self.assertFalse(
                any(
                    item["path"].endswith(
                        ("forgejo-data.tar.gz", "webhook-sink-data.tar.gz")
                    )
                    for item in public_manifest["files"]
                )
            )

    def test_rejects_unbound_archive_or_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            self._write_bundle(source, "prefix")
            extra = source / "extra"
            extra.mkdir()
            (extra / "forgejo-data.tar.gz").write_bytes(b"unbound")

            with self.assertRaisesRegex(
                ValueError,
                "every native restore archive",
            ):
                build_public_archive(
                    source,
                    root / "public-a",
                    expected_restore_bundle_count=1,
                )

            (extra / "forgejo-data.tar.gz").unlink()
            (source / "bundles" / "prefix" / "forgejo-data.tar.gz").write_bytes(
                b"tampered"
            )
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                build_public_archive(
                    source,
                    root / "public-b",
                    expected_restore_bundle_count=1,
                )

    def test_rejects_credential_files_instead_of_silently_omitting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            self._write_bundle(source, "prefix")
            (source / "credentials.json").write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "credential-like"):
                build_public_archive(
                    source,
                    root / "public",
                    expected_restore_bundle_count=1,
                )


if __name__ == "__main__":
    unittest.main()
