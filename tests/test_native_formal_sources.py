import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.native_formal_sources import (
    NativeFormalSourceError,
    load_exact_file_manifest,
)


class NativeFormalSourcesTest(unittest.TestCase):
    def _manifest(self, root: Path) -> Path:
        source = root / "bundle" / "payload.json"
        source.parent.mkdir()
        source.write_text('{"ok":true}\n', encoding="utf-8")
        payload = {
            "schema_version": "0.1",
            "excluded_files": ["files.json"],
            "file_count": 1,
            "total_bytes": source.stat().st_size,
            "files": [
                {
                    "path": "payload.json",
                    "bytes": source.stat().st_size,
                    "sha256": hashlib.sha256(
                        source.read_bytes()
                    ).hexdigest(),
                }
            ],
        }
        manifest = source.parent / "files.json"
        manifest.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest

    def test_loads_an_exact_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest_path = self._manifest(root)
            manifest = load_exact_file_manifest(
                root,
                manifest_path,
                label="fixture",
            )
            self.assertEqual(manifest.relative_path, "bundle/files.json")
            self.assertEqual(
                manifest.require_file(
                    manifest.root / "payload.json",
                    label="payload",
                )["path"],
                "payload.json",
            )

    def test_rejects_unlisted_or_drifted_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest_path = self._manifest(root)
            (manifest_path.parent / "payload.json").write_text(
                '{"ok":false}\n',
                encoding="utf-8",
            )
            with self.assertRaises(NativeFormalSourceError):
                load_exact_file_manifest(
                    root,
                    manifest_path,
                    label="fixture",
                )

    def test_rejects_unlisted_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest_path = self._manifest(root)
            (manifest_path.parent / "extra.txt").write_text(
                "extra",
                encoding="utf-8",
            )
            with self.assertRaises(NativeFormalSourceError):
                load_exact_file_manifest(
                    root,
                    manifest_path,
                    label="fixture",
                )


if __name__ == "__main__":
    unittest.main()
