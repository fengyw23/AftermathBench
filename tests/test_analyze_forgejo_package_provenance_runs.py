from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "analyze_forgejo_package_provenance_runs.py"
)
_SPEC = importlib.util.spec_from_file_location("package_analysis", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


class ForgejoPackageProvenanceAnalysisTest(unittest.TestCase):
    def _report(self, variant: str, *, delete: bool) -> dict:
        query_names = [
            "get_package_version",
            "list_package_files",
            "get_repository_file",
            "get_repository_file",
            "list_releases",
            "list_hooks",
            "get_webhook_history",
            "get_webhook_history",
            "list_external_deliveries",
        ]
        mutations = ["delete_package_version"] if delete else []
        mutations.append("create_package_index_release")
        return {
            "family": "forgejo-package-provenance",
            "model": "model-a",
            "variant": variant,
            "execution_control": False,
            "turns": [
                {
                    "tool_calls": [
                        {"name": name, "arguments": {}}
                        for name in [*query_names, *mutations]
                    ]
                }
            ],
            "evaluation": {"passed": True, "checks": {"goal": True}},
            "trajectory_diagnostics": {"primary_error": None},
        }

    def test_reports_opposite_scope_for_same_inventory_pair(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reports = (
                self._report(
                    "r2_package_complete_index_missing",
                    delete=False,
                ),
                self._report(
                    "r2_package_corrupt_binary_index_missing",
                    delete=True,
                ),
            )
            for index, report in enumerate(reports):
                (root / f"run-{index}.json").write_text(
                    json.dumps(report),
                    encoding="utf-8",
                )
            result = _MODULE.analyze(root)
        model = result["model_results"]["model-a"]
        self.assertEqual(model["task_pass_rate"], 1.0)
        self.assertTrue(model["same_inventory_pair_scope_polarity_correct"])
        self.assertEqual(model["evidence_complete_before_first_write_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
