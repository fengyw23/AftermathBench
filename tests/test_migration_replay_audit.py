from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.integrations.kubernetes_migration_faults import (
    KUBERNETES_MIGRATION_VARIANTS,
    SURFACE_ERROR,
)
from aftermath_bench.migration_replay_audit import (
    EXPECTED_DIRECTIONS,
    audit_migration_replay,
)


class MigrationReplayAuditTest(unittest.TestCase):
    def _materialize(self, root: Path) -> None:
        observations = {
            "change_request_not_reached": ("1", "v1", 0),
            "preparation_escaped_migration_failed": ("1", "v1", 1),
            "schema_committed_cutover_pending": ("2", "v1", 1),
            "cutover_and_publication_committed": ("2", "v2", 1),
        }
        for variant in KUBERNETES_MIGRATION_VARIANTS:
            epoch, version, jobs = observations[variant]
            (root / f"{variant}.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "surface_result": SURFACE_ERROR,
                        "prefix_fingerprint": "same-prefix",
                        "observed": {
                            "schema_epoch": epoch,
                            "service_version": version,
                            "migration_job_count": jobs,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / f"{variant}-reference.json").write_text(
                json.dumps(
                    {
                        "semantic_recovery_direction": EXPECTED_DIRECTIONS[variant],
                        "mutation_tools": ["patch"] * 4,
                        "control_error": None,
                        "evaluation": {"passed": True},
                    }
                ),
                encoding="utf-8",
            )

    def test_accepts_four_objective_directions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._materialize(root)
            report = audit_migration_replay(root)
        self.assertTrue(report["passed"], report["checks"])
        self.assertEqual(
            len(set(report["observed"]["semantic_directions"].values())),
            4,
        )

    def test_rejects_direction_label_not_supported_by_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._materialize(root)
            path = root / "change_request_not_reached-reference.json"
            report = json.loads(path.read_text(encoding="utf-8"))
            report["semantic_recovery_direction"] = "forward_complete"
            path.write_text(json.dumps(report), encoding="utf-8")
            audit = audit_migration_replay(root)
        self.assertFalse(audit["passed"])
        self.assertFalse(audit["checks"]["directions_match_objective_boundaries"])


if __name__ == "__main__":
    unittest.main()
