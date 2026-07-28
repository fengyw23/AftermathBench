from __future__ import annotations

import hashlib
import json
import unittest

from scripts.verify_native_freeze import verify_freeze


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NativeFreezeTest(unittest.TestCase):
    def test_native_freeze_detects_prefix_drift(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = root / "scenario.json"
            prefix = root / "prefix.json"
            freeze = root / "freeze.json"
            scenario.write_text(
                json.dumps({"scenario_id": "holdout-001"}),
                encoding="utf-8",
            )
            prefix.write_text(json.dumps({"state": 1}), encoding="utf-8")
            freeze.write_text(
                json.dumps(
                    {
                        "scenario_id": "holdout-001",
                        "scenario_sha256": _sha256(scenario),
                        "prefix_sha256": _sha256(prefix),
                    }
                ),
                encoding="utf-8",
            )
            observed = verify_freeze(
                freeze_path=freeze,
                scenario_path=scenario,
                prefix_path=prefix,
            )
            self.assertEqual(observed["scenario_id"], "holdout-001")

            prefix.write_text(json.dumps({"state": 2}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                verify_freeze(
                    freeze_path=freeze,
                    scenario_path=scenario,
                    prefix_path=prefix,
                )


if __name__ == "__main__":
    unittest.main()
