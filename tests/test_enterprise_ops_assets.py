import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from aftermath_bench.integrations.enterprise_ops_assets import (
    infer_insert_schema,
    materialize_seed_sqlite,
)


TEST_SEED = """
INSERT INTO incident (incident_id, number, priority) VALUES
('inc-1', 'INC0001', 3),
('inc-2', 'INC0002', 1);
INSERT INTO incident_sla
    (incident_sla_id, incident_id, stage, has_breached)
VALUES ('sla-1', 'inc-1', 'active', 0);
"""


class EnterpriseOpsAssetTest(unittest.TestCase):
    def test_schema_is_inferred_from_insert_headers(self) -> None:
        self.assertEqual(
            infer_insert_schema(TEST_SEED),
            {
                "incident": ("incident_id", "number", "priority"),
                "incident_sla": (
                    "incident_sla_id",
                    "incident_id",
                    "stage",
                    "has_breached",
                ),
            },
        )

    def test_seed_materializes_as_queryable_sqlite(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "seed.sqlite"
            manifest = materialize_seed_sqlite(
                TEST_SEED,
                database,
                source_entry="test.sql",
                source_sha256="test",
            )
            self.assertEqual(manifest.table_count, 2)
            self.assertEqual(manifest.row_count, 3)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT number FROM incident WHERE priority = 1"
                    ).fetchone(),
                    ("INC0002",),
                )


if __name__ == "__main__":
    unittest.main()
