from __future__ import annotations

import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import scripts.extract_sealed_hidden_bundle as extractor
import scripts.recover_forgejo_evaluation_credentials as credentials
import scripts.summarize_consumed_hidden_evaluation as summarizer
from aftermath_bench.native_freeze import append_usage_event


class HiddenBundleExtractionTests(unittest.TestCase):
    def test_extracts_regular_private_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "bundle.tar.gz"
            payload = b"{}\n"
            with tarfile.open(archive_path, "w:gz") as archive:
                member = tarfile.TarInfo("private/scenario/scenario.json")
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
            with patch(
                "sys.argv",
                [
                    "extract",
                    "--archive",
                    str(archive_path),
                    "--destination",
                    str(root / "output"),
                ],
            ):
                self.assertEqual(extractor.main(), 0)
            self.assertEqual(
                (root / "output/private/scenario/scenario.json").read_bytes(),
                payload,
            )

    def test_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "bundle.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                member = tarfile.TarInfo("../secret")
                member.size = 1
                archive.addfile(member, io.BytesIO(b"x"))
            with patch(
                "sys.argv",
                [
                    "extract",
                    "--archive",
                    str(archive_path),
                    "--destination",
                    str(root / "output"),
                ],
            ), self.assertRaises(ValueError):
                extractor.main()


class ForgejoCredentialRecoveryTests(unittest.TestCase):
    @patch.object(credentials, "ForgejoStack")
    def test_issues_ephemeral_password_and_raw_token(self, stack_type: Mock) -> None:
        stack = stack_type.return_value
        stack.run.side_effect = [
            Mock(stdout="password updated\n"),
            Mock(stdout="token-value\n"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "credentials.json"
            with patch(
                "sys.argv",
                [
                    "recover",
                    "--compose-file",
                    str(root / "compose.yaml"),
                    "--username",
                    "owner",
                    "--output",
                    str(output),
                ],
            ):
                self.assertEqual(credentials.main(), 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["username"], "owner")
            self.assertEqual(result["token"], "token-value")
            self.assertTrue(result["password"])
            self.assertEqual(stack.run.call_count, 2)
            password_call = stack.run.call_args_list[0].args
            self.assertIn("--must-change-password=false", password_call)


class HiddenConsumptionSummaryTests(unittest.TestCase):
    def test_publishes_aggregate_without_run_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commitment = root / "commitment.json"
            ledger = root / "ledger.json"
            model_summary = root / "summary.json"
            output = root / "result.json"
            commitment.write_text(
                json.dumps(
                    {
                        "scenario_id": "hidden-001",
                        "public_commitment_sha256": "a" * 64,
                    }
                ),
                encoding="utf-8",
            )
            append_usage_event(
                ledger_path=ledger,
                event="frozen",
                details={"public_commitment_sha256": "a" * 64},
            )
            append_usage_event(
                ledger_path=ledger,
                event="evaluation_locked",
                details={"evaluation_id": "run"},
            )
            append_usage_event(
                ledger_path=ledger,
                event="consumed",
                details={"evaluation_id": "run"},
            )
            model_summary.write_text(
                json.dumps(
                    {
                        "completed_runs": 8,
                        "run_errors": [],
                        "task_pass_rate": 0.25,
                        "matched_group_count": 1,
                        "matched_group_success_rate": 0.0,
                        "component_pass_rates": {"preservation": 0.5},
                        "failure_type_counts": {"scope_failure": 4},
                        "execution_control_counts": {"false": 8},
                        "reports": [{"path": "/private/trajectory.json"}],
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "sys.argv",
                [
                    "summarize",
                    "--commitment",
                    str(commitment),
                    "--usage-ledger",
                    str(ledger),
                    "--model-summary",
                    str(model_summary),
                    "--provider-profile",
                    "zhipu",
                    "--model",
                    "glm-5.2",
                    "--evaluation-run-id",
                    "2",
                    "--freeze-run-id",
                    "1",
                    "--freeze-artifact-id",
                    "3",
                    "--freeze-artifact-digest",
                    "sha256:" + "b" * 64,
                    "--ciphertext-sha256",
                    "c" * 64,
                    "--output",
                    str(output),
                ],
            ):
                self.assertEqual(summarizer.main(), 0)
            result = output.read_text(encoding="utf-8")
            self.assertNotIn("trajectory.json", result)
            self.assertEqual(
                json.loads(result)["lifecycle_status"], "consumed"
            )


if __name__ == "__main__":
    unittest.main()
