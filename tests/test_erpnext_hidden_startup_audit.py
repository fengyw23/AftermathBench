from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.audit_erpnext_hidden_startup_failure as audit

ROOT = Path(__file__).resolve().parents[1]


class ERPNextHiddenStartupAuditTests(unittest.TestCase):
    def test_aggregate_audit_contains_no_private_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "private"
            model = private / "model" / "repetition-01"
            model.mkdir(parents=True)
            (model / "credential-smoke.log").write_text(
                '{"passed": false, "secret": "must-not-escape"}\n',
                encoding="utf-8",
            )
            (model / "credential-probe-restore.log").write_text(
                "service did not become ready: http://127.0.0.1:8080/api/method/ping\n"
                "hidden document must-not-escape\n",
                encoding="utf-8",
            )
            for index in range(2):
                bundle = private / "bundles" / f"boundary-secret-{index}"
                bundle.mkdir(parents=True)
                (bundle / "bundle.json").write_text(
                    json.dumps(
                        {
                            "schema_version": "1.1",
                            "files": {"site_config": {"path": "private"}},
                        }
                    ),
                    encoding="utf-8",
                )
            (private / "usage-ledger.json").write_text(
                json.dumps({"events": [{"event": "frozen"}]}),
                encoding="utf-8",
            )
            output = Path(directory) / "public.json"
            with patch(
                "sys.argv",
                [
                    "audit",
                    "--private-root",
                    str(private),
                    "--output",
                    str(output),
                ],
            ):
                self.assertEqual(audit.main(), 0)
            text = output.read_text(encoding="utf-8")
            payload = json.loads(text)
            self.assertFalse(payload["credential_smoke_passed"])
            self.assertTrue(payload["credential_probe_restore_present"])
            self.assertEqual(
                payload["credential_probe_restore_failure_class"],
                "erpnext_readiness_timeout",
            )
            self.assertEqual(payload["site_config_bound_bundle_count"], 2)
            self.assertNotIn("must-not-escape", text)
            self.assertNotIn("secret-", text)

    def test_workflow_cannot_call_a_model_or_publish_private_files(self) -> None:
        text = (
            ROOT / ".github" / "workflows" / "erpnext-hidden-startup-audit.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("run-native-model", text)
        self.assertNotIn("AFTERMATH_API_KEY", text)
        self.assertIn("publish-aggregate-verdict", text)
        self.assertIn("credential_smoke_passed", text)
        upload = text.index("Upload redacted startup audit only")
        purge = text.index("Purge plaintext and encrypted inputs")
        section = text[upload:purge]
        self.assertIn("hidden-startup-audit/public/", section)
        self.assertNotIn("hidden-startup-unsealed", section)


if __name__ == "__main__":
    unittest.main()
