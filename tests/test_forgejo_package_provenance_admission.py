from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from scripts.build_forgejo_package_provenance_admission import (
    _validate_nonmonotonic_pair,
)


class ForgejoPackageProvenanceAdmissionTest(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[dict, dict, list[dict]]:
        blueprint = {
            "admission_profile": {
                "adaptive_recovery": {
                    "requires_same_inventory_opposite_scope_pair": True
                }
            }
        }
        prefix = {
            "expected_package_files": [{"name": "agent.tar.gz", "sha256": "approved"}]
        }
        states = {
            "r2_package_complete_index_missing": "approved",
            "r2_package_corrupt_binary_index_missing": "stale-build",
        }
        for variant, digest in states.items():
            (root / f"{variant}-boundary.json").write_text(
                json.dumps(
                    {
                        "latest_attempt": {"tool": "create_package_index_release"},
                        "failure_boundary_evidence": {
                            "target_package_files": [
                                {
                                    "name": "agent.tar.gz",
                                    "content_sha256": digest,
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
        reports = [
            {
                "variant": "r2_package_complete_index_missing",
                "mutation_tools": ["create_package_index_release"],
                "evaluation": {"passed": True},
            },
            {
                "variant": "r2_package_corrupt_binary_index_missing",
                "mutation_tools": [
                    "delete_package_version",
                    "upload_package_file_from_repository",
                ],
                "evaluation": {"passed": True},
            },
        ]
        return blueprint, prefix, reports

    def test_accepts_same_inventory_with_opposite_native_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blueprint, prefix, reports = self._fixture(root)
            checks = _validate_nonmonotonic_pair(
                blueprint=blueprint,
                prefix=prefix,
                runtime_directory=root,
                reports=reports,
            )
        self.assertTrue(all(checks.values()))

    def test_rejects_a_reference_that_never_replaces_corrupt_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blueprint, prefix, reports = self._fixture(root)
            reports[1]["mutation_tools"] = ["create_package_index_release"]
            with self.assertRaisesRegex(RuntimeError, "corrupt_scope_replaces"):
                _validate_nonmonotonic_pair(
                    blueprint=blueprint,
                    prefix=prefix,
                    runtime_directory=root,
                    reports=reports,
                )


if __name__ == "__main__":
    unittest.main()
