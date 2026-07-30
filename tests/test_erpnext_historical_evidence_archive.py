from __future__ import annotations

import hashlib
import unittest
from collections import Counter
from pathlib import Path

from aftermath_bench.schema import repository_root
from aftermath_bench.strict_json import load_json_strict

ARCHIVE_RELATIVE = Path(
    "data/evidence/erpnext-sales-return-native-historical-30425865276"
)
VARIANTS = {
    "request_not_reached",
    "database_committed_response_lost",
    "after_commit_enqueue_failed",
    "async_job_pending",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ERPNextHistoricalEvidenceArchiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = repository_root()
        cls.archive = cls.root / ARCHIVE_RELATIVE
        cls.provenance = load_json_strict(cls.archive / "provenance.json")

    def test_provenance_fixes_source_identity_and_non_formal_status(self) -> None:
        manifest = self.provenance
        source = manifest["source"]

        self.assertEqual(manifest["scenario_id"], "erpnext-sales-return-dev-001")
        self.assertIs(manifest["historical_only"], True)
        self.assertIs(manifest["formal_evidence"], False)
        self.assertIs(manifest["current_gate_compatible"], False)
        self.assertIs(manifest["legacy_schema"], True)
        self.assertEqual(
            manifest["source_schema_versions"],
            {
                "boundary": "0.1",
                "reference": "0.1",
                "prefix_validation": None,
            },
        )
        self.assertEqual(source["workflow_run_id"], 30425865276)
        self.assertEqual(source["artifact_id"], 8714029126)
        self.assertEqual(
            source["producer_commit"],
            "2483724cbd27c4162ab203eaca8ebf49eab35c12",
        )
        self.assertEqual(
            source["artifact_zip_sha256"],
            "d81eb081efd37006c3a1f8e25d4c4ada71c110676eb00ffc067cdd34186e2cca",
        )
        self.assertEqual(source["artifact_zip_bytes"], 543411)
        self.assertGreaterEqual(len(manifest["gate_limitations"]), 4)

    def test_selected_inventory_is_minimal_and_byte_bound(self) -> None:
        manifest = self.provenance
        selection = manifest["selection"]
        records = manifest["files"]

        self.assertEqual(selection["artifact_json_count"], 72)
        self.assertEqual(selection["exact_duplicate_json_count"], 7)
        self.assertEqual(selection["missing_json_count"], 65)
        self.assertEqual(selection["selected_json_count"], 9)
        self.assertEqual(len(records), 9)
        self.assertEqual(
            Counter(record["role"] for record in records),
            Counter({"boundary": 4, "reference": 4, "prefix_validation": 1}),
        )
        self.assertEqual(
            {record["variant"] for record in records if record["role"] == "boundary"},
            VARIANTS,
        )
        self.assertEqual(
            {record["variant"] for record in records if record["role"] == "reference"},
            VARIANTS,
        )

        archive_paths: set[str] = set()
        for record in records:
            self.assertIs(record["copied_without_reserialization"], True)
            relative = Path(record["archive_path"])
            self.assertEqual(relative.suffix, ".json")
            self.assertTrue(relative.is_relative_to(ARCHIVE_RELATIVE))
            self.assertNotIn(str(relative), archive_paths)
            archive_paths.add(str(relative))

            path = self.root / relative
            self.assertTrue(path.is_file(), path)
            self.assertEqual(path.stat().st_size, record["bytes"], path)
            self.assertEqual(_sha256(path), record["sha256"], path)

        actual_json = {
            str(path.relative_to(self.root))
            for path in (self.archive / "raw").rglob("*.json")
        }
        self.assertEqual(actual_json, archive_paths)
        self.assertFalse(list(self.archive.rglob("*.zip")))
        self.assertFalse(list(self.archive.rglob("*.log")))

    def test_legacy_payloads_match_variants_but_not_current_envelope(self) -> None:
        for record in self.provenance["files"]:
            if record["role"] not in {"boundary", "reference"}:
                continue
            payload = load_json_strict(self.root / record["archive_path"])
            self.assertEqual(payload["schema_version"], "0.1")
            self.assertEqual(payload["scenario_id"], "erpnext-sales-return-dev-001")
            self.assertEqual(payload["variant"], record["variant"])

            if record["role"] == "boundary":
                self.assertIn("boundary_validation", payload)
                self.assertNotIn("formal_evidence", payload)
                self.assertNotIn("dependencies", payload)
            else:
                self.assertIn("reference_trace", payload)
                self.assertIn("evaluation", payload)

    def test_reference_hashes_match_the_existing_replay_index(self) -> None:
        replay = load_json_strict(
            self.root
            / "data/scenarios/erpnext-sales-return-dev-001/artifacts/replay_evidence.json"
        )
        expected = {
            capture["variant"]: capture["source_report_sha256"]
            for capture in replay["captures"]
        }
        archived = {
            record["variant"]: record["sha256"]
            for record in self.provenance["files"]
            if record["role"] == "reference"
        }
        self.assertEqual(archived, expected)

    def test_archive_contains_no_obvious_credentials(self) -> None:
        forbidden = (
            "api_key",
            "api_secret",
            "authorization",
            "bearer",
            "password",
            "credential",
            "secret",
        )
        for record in self.provenance["files"]:
            text = (self.root / record["archive_path"]).read_text(
                encoding="utf-8"
            )
            lowered = text.lower()
            for token in forbidden:
                self.assertNotIn(token, lowered, (record["archive_path"], token))


if __name__ == "__main__":
    unittest.main()
