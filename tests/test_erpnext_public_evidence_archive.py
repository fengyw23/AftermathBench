import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_erpnext_public_evidence_archive import (
    build_public_archive,
)


class ERPNextPublicEvidenceArchiveTest(unittest.TestCase):
    def _bundle(self, root: Path, name: str) -> None:
        bundle = root / "bundles" / name
        bundle.mkdir(parents=True)
        files = {}
        mapping = {
            "database": "database.sql",
            "site_config": "site-config.tar",
            "redis_queue": "redis-queue.tar",
            "gateway_audit": "gateway-audit.tar",
            "remittance_audit": "remittance-audit.tar",
        }
        for key, filename in mapping.items():
            path = bundle / filename
            path.write_bytes(f"{name}-{filename}".encode())
            files[key] = {
                "path": filename,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        (bundle / "bundle.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.1",
                    "capture_mode": "simultaneous_service_quiescence",
                    "running_services": ["backend"],
                    "files": files,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_omits_native_state_but_binds_its_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "native"
            source.mkdir()
            self._bundle(source, "prefix")
            (source / "report.json").write_text(
                '{"passed":true}\n',
                encoding="utf-8",
            )
            output = base / "public"
            result = build_public_archive(
                source,
                output,
                expected_restore_bundle_count=1,
            )
            self.assertTrue(result["passed"])
            self.assertFalse((output / "bundles" / "prefix" / "database.sql").exists())
            omissions = json.loads(
                (output / "omissions.json").read_text(encoding="utf-8")
            )
            self.assertEqual(omissions["omitted_file_count"], 5)
            self.assertTrue((output / "report.json").is_file())

    def test_rejects_a_drifted_native_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "native"
            source.mkdir()
            self._bundle(source, "prefix")
            (source / "bundles" / "prefix" / "database.sql").write_bytes(b"drift")
            with self.assertRaises(ValueError):
                build_public_archive(
                    source,
                    base / "public",
                    expected_restore_bundle_count=1,
                )


if __name__ == "__main__":
    unittest.main()
