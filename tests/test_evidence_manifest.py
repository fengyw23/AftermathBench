from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.evidence_manifest import build_file_manifest


class EvidenceManifestTest(unittest.TestCase):
    def test_hashes_relative_files_and_honors_exclusions(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "a.txt").write_text("alpha", encoding="utf-8")
            (root / "nested" / "b.txt").write_text(
                "beta",
                encoding="utf-8",
            )
            (root / "manifest.json").write_text("exclude", encoding="utf-8")
            result = build_file_manifest(
                root,
                exclude={"manifest.json"},
            )

        self.assertEqual(result["file_count"], 2)
        self.assertEqual(result["excluded_files"], ["manifest.json"])
        self.assertEqual(
            [item["path"] for item in result["files"]],
            ["a.txt", "nested/b.txt"],
        )
        self.assertEqual(
            result["files"][0]["sha256"],
            hashlib.sha256(b"alpha").hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
