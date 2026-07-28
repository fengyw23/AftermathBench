import importlib.util
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


def _load_audit_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "audit_enterprise_ops.py"
    spec = importlib.util.spec_from_file_location("audit_enterprise_ops", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class EnterpriseOpsAuditTest(unittest.TestCase):
    def test_archive_reports_union_and_per_snapshot_scale(self) -> None:
        module = _load_audit_module()
        with TemporaryDirectory() as directory:
            archive_path = Path(directory) / "seeds.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "root/hybrid/dbs/a.sql",
                    "INSERT INTO users (id, name) VALUES ('1', 'Ada');",
                )
                archive.writestr(
                    "root/hybrid/dbs/b.sql",
                    "\n".join(
                        (
                            "INSERT INTO users (id, name) VALUES ('2', 'Grace');",
                            "INSERT INTO teams (id) VALUES ('t1');",
                        )
                    ),
                )
            report = module.audit_seed_archive(archive_path)
            hybrid = report["domains"]["hybrid"]
            self.assertEqual(hybrid["sql_file_count"], 2)
            self.assertEqual(hybrid["union_table_count"], 2)
            self.assertEqual(hybrid["max_tables_in_one_snapshot"], 2)
            self.assertEqual(hybrid["min_tables_in_one_snapshot"], 1)
            json.dumps(report)


if __name__ == "__main__":
    unittest.main()

