from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.verify_hidden_evaluation_novelty as verifier


class VerifyHiddenEvaluationNoveltyTests(unittest.TestCase):
    def _run(self, scenario_id: str, retired_id: str) -> int:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = root / "scenario.json"
            registry = root / "registry"
            registry.mkdir()
            scenario.write_text(
                json.dumps({"scenario_id": scenario_id}), encoding="utf-8"
            )
            (registry / "invalidation.json").write_text(
                json.dumps(
                    {
                        "record_type": "hidden_evaluation_invalidation",
                        "scenario_id": retired_id,
                        "disposition": {"hidden_instance_reusable": False},
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "sys.argv",
                [
                    "verify",
                    "--scenario",
                    str(scenario),
                    "--registry-root",
                    str(registry),
                ],
            ):
                return verifier.main()

    def test_rejects_a_retired_scenario_identity(self) -> None:
        self.assertEqual(self._run("hidden-001", "hidden-001"), 2)

    def test_accepts_a_fresh_scenario_identity(self) -> None:
        self.assertEqual(self._run("hidden-002", "hidden-001"), 0)


if __name__ == "__main__":
    unittest.main()
