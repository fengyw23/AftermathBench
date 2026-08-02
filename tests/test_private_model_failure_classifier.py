from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.classify_private_model_failures as classifier


class PrivateModelFailureClassifierTests(unittest.TestCase):
    def test_outputs_counts_without_private_text_or_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / "runs"
            runs.mkdir()
            (runs / "secret-a-attempt-1.log").write_text(
                "TimeoutError: hidden-name-123 timed out",
                encoding="utf-8",
            )
            (runs / "secret-b-attempt-1.log").write_text(
                "RuntimeError: model endpoint returned HTTP 429: private body",
                encoding="utf-8",
            )
            (runs / "secret-c-attempt-1.log").write_text(
                "credentials=/private/credentials.json\nValueError: hidden",
                encoding="utf-8",
            )
            output = root / "result.json"
            with patch(
                "sys.argv",
                [
                    "classify",
                    "--run-directory",
                    str(runs),
                    "--output",
                    str(output),
                ],
            ):
                self.assertEqual(classifier.main(), 0)
            text = output.read_text(encoding="utf-8")
            payload = json.loads(text)
            self.assertEqual(payload["attempt_log_count"], 3)
            self.assertEqual(
                payload["classification_counts"],
                {
                    "provider_http_error": 1,
                    "provider_timeout": 1,
                    "unknown": 1,
                },
            )
            self.assertEqual(
                payload["terminal_exception_type_counts"],
                {"RuntimeError": 1, "ValueError": 1},
            )
            self.assertNotIn("hidden-name-123", text)
            self.assertNotIn("private body", text)
            self.assertNotIn("secret-a", text)


if __name__ == "__main__":
    unittest.main()
