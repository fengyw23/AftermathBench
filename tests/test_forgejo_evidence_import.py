from __future__ import annotations

import unittest

from aftermath_bench.forgejo_evidence_import import (
    ForgejoEvidenceImportError,
    ForgejoEvidenceImportGate,
    build_import_provenance,
    select_artifact,
    validate_publication_status,
    validate_source_run,
)

RUN_ID = 30606890872
COMMIT = "1" * 40
DIGEST = "sha256:" + "2" * 64


def gate_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "stage": "forgejo-public-dev-evidence-import",
        "source_run_id": RUN_ID,
        "source_commit": COMMIT,
        "artifact_name": f"forgejo-publication-public-dev-evidence-{RUN_ID}",
        "artifact_digest": DIGEST,
        "expected_cases": 8,
        "minimum_pass_rate": 0.8,
        "scenario_id": "forgejo-public-dev-002",
        "formal_relative_root": "data/evidence/formal/release/forgejo/family/dev-002",
    }


class ForgejoEvidenceImportTests(unittest.TestCase):
    def test_gate_is_exact_and_safe(self) -> None:
        gate = ForgejoEvidenceImportGate.from_mapping(gate_payload())
        self.assertEqual(gate.source_run_id, RUN_ID)
        self.assertEqual(
            gate.github_environment()["SOURCE_ARTIFACT"], gate.artifact_name
        )
        for key, value in (
            ("extra", True),
            ("source_commit", "short"),
            ("minimum_pass_rate", 0.7),
            ("formal_relative_root", "../outside"),
        ):
            payload = gate_payload()
            payload[key] = value
            with self.subTest(key=key), self.assertRaises(ForgejoEvidenceImportError):
                ForgejoEvidenceImportGate.from_mapping(payload)

    def test_run_and_artifact_are_exactly_bound(self) -> None:
        gate = ForgejoEvidenceImportGate.from_mapping(gate_payload())
        run = {
            "id": RUN_ID,
            "head_sha": COMMIT,
            "status": "completed",
            "conclusion": "success",
            "path": ".github/workflows/forgejo-publication-public-dev.yml",
        }
        validate_source_run(run, gate=gate)
        artifact = {
            "id": 9,
            "name": gate.artifact_name,
            "expired": False,
            "size_in_bytes": 1024,
            "digest": DIGEST,
        }
        selected = select_artifact({"artifacts": [artifact]}, gate=gate)
        self.assertEqual(selected["id"], 9)
        provenance = build_import_provenance(
            gate=gate, artifact=artifact, import_commit="3" * 40
        )
        self.assertEqual(provenance["artifact"]["digest"], DIGEST)
        with self.assertRaises(ForgejoEvidenceImportError):
            validate_source_run(run | {"conclusion": "failure"}, gate=gate)
        with self.assertRaises(ForgejoEvidenceImportError):
            select_artifact(
                {"artifacts": [artifact | {"digest": "sha256:" + "4" * 64}]},
                gate=gate,
            )

    def test_publication_status_requires_complete_eight_of_eight_control(self) -> None:
        gate = ForgejoEvidenceImportGate.from_mapping(gate_payload())
        status = {
            "schema_version": "1.0",
            "artifact_type": "forgejo_public_development_publication_status",
            "formal_complete": True,
            "control_gate_pass": True,
            "release_promotion_eligible": True,
            "control": {
                "summary_valid": True,
                "expected_cases": 8,
                "completed_runs": 8,
                "passed_runs": 8,
                "task_pass_rate": 1.0,
                "minimum_pass_rate": 0.8,
            },
            "formal": {
                "declarations_present": True,
                "declarations_sha256": "a" * 64,
            },
            "safety": {
                "provider_secret_scan_passed": True,
                "scenario_present": True,
                "scenario_sha256": "b" * 64,
            },
        }
        validate_publication_status(
            status,
            gate=gate,
            scenario_sha256="b" * 64,
            declarations_sha256="a" * 64,
        )
        with self.assertRaises(ForgejoEvidenceImportError):
            validate_publication_status(
                status | {"release_promotion_eligible": False},
                gate=gate,
                scenario_sha256="b" * 64,
                declarations_sha256="a" * 64,
            )


if __name__ == "__main__":
    unittest.main()
