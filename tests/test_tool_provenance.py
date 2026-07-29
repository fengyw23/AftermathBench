from __future__ import annotations

import unittest

from aftermath_bench.native_model_runner import (
    NATIVE_RETURN_TOOL_DEFINITIONS,
)
from aftermath_bench.native_forgejo_family import (
    FORGEJO_TOOL_DEFINITIONS,
)
from aftermath_bench.native_kubernetes_family import (
    KUBERNETES_TOOL_DEFINITIONS,
)
from aftermath_bench.native_sales_family import SALES_RETURN_TOOL_DEFINITIONS
from aftermath_bench.schema import repository_root
from aftermath_bench.tool_provenance import (
    load_tool_provenance,
    validate_tool_provenance,
)


class ToolProvenanceTest(unittest.TestCase):
    def test_erpnext_manifest_covers_every_exposed_tool(self) -> None:
        path = (
            repository_root()
            / "data"
            / "runtimes"
            / "erpnext-v15"
            / "tool_provenance.json"
        )
        report = validate_tool_provenance(
            load_tool_provenance(path),
            NATIVE_RETURN_TOOL_DEFINITIONS,
        )
        self.assertTrue(report.passed, report.failures)

    def test_sales_return_manifest_covers_every_exposed_tool(self) -> None:
        path = (
            repository_root()
            / "data"
            / "runtimes"
            / "erpnext-v15"
            / "sales_return_tool_provenance.json"
        )
        report = validate_tool_provenance(
            load_tool_provenance(path),
            SALES_RETURN_TOOL_DEFINITIONS,
        )
        self.assertTrue(report.passed, report.failures)

    def test_forgejo_manifest_covers_every_exposed_tool(self) -> None:
        path = (
            repository_root()
            / "data"
            / "runtimes"
            / "forgejo-main"
            / "tool_provenance.json"
        )
        report = validate_tool_provenance(
            load_tool_provenance(path),
            FORGEJO_TOOL_DEFINITIONS,
        )
        self.assertTrue(report.passed, report.failures)

    def test_kubernetes_manifest_covers_every_exposed_tool(self) -> None:
        path = (
            repository_root()
            / "data"
            / "runtimes"
            / "kubernetes-v1.34"
            / "tool_provenance.json"
        )
        report = validate_tool_provenance(
            load_tool_provenance(path),
            KUBERNETES_TOOL_DEFINITIONS,
        )
        self.assertTrue(report.passed, report.failures)


if __name__ == "__main__":
    unittest.main()
