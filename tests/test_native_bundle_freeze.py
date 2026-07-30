from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.native_freeze import (
    append_usage_event,
    build_frozen_bundle,
    file_sha256,
    verify_frozen_bundle,
)


class NativeBundleFreezeTests(unittest.TestCase):
    def _bundle(self, root: Path) -> tuple[Path, Path]:
        instance = root / "instance.json"
        instance_payload = {"scenario_id": "hidden-1", "fact": "alpha"}
        instance.write_text(
            json.dumps(instance_payload),
            encoding="utf-8",
        )
        import hashlib

        semantic_hash = hashlib.sha256(
            json.dumps(
                instance_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        scenario = root / "scenario.json"
        scenario.write_text(
            json.dumps(
                {
                    "scenario_id": "hidden-1",
                    "instance_spec_sha256": semantic_hash,
                }
            ),
            encoding="utf-8",
        )
        (root / "variant.snapshot").write_bytes(b"native state")
        return scenario, instance

    def test_every_bound_file_changes_the_root_commitment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario, instance = self._bundle(root)
            first = build_frozen_bundle(
                bundle_root=root,
                scenario_path=scenario,
                instance_spec_path=instance,
                source_commit="abc",
                runtime_revision="forgejo-revision",
                salt="fixed-salt",
            )
            (root / "variant.snapshot").write_bytes(b"changed state")
            second = build_frozen_bundle(
                bundle_root=root,
                scenario_path=scenario,
                instance_spec_path=instance,
                source_commit="abc",
                runtime_revision="forgejo-revision",
                salt="fixed-salt",
            )

            self.assertNotEqual(
                first.private_attestation["bundle_root_sha256"],
                second.private_attestation["bundle_root_sha256"],
            )
            self.assertNotEqual(
                first.public_commitment["public_commitment_sha256"],
                second.public_commitment["public_commitment_sha256"],
            )

    def test_usage_ledger_is_separate_from_frozen_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario, instance = self._bundle(root)
            ledger = root / "usage-ledger.json"
            first = build_frozen_bundle(
                bundle_root=root,
                scenario_path=scenario,
                instance_spec_path=instance,
                source_commit="abc",
                runtime_revision="forgejo-revision",
                salt="fixed-salt",
                excluded_relative_paths=("usage-ledger.json",),
            )
            append_usage_event(
                ledger_path=ledger,
                event="frozen",
                details={
                    "public_commitment_sha256": first.public_commitment[
                        "public_commitment_sha256"
                    ]
                },
            )
            append_usage_event(
                ledger_path=ledger,
                event="evaluation_locked",
                details={"model": "control"},
            )
            second = build_frozen_bundle(
                bundle_root=root,
                scenario_path=scenario,
                instance_spec_path=instance,
                source_commit="abc",
                runtime_revision="forgejo-revision",
                salt="fixed-salt",
                excluded_relative_paths=("usage-ledger.json",),
            )

            self.assertEqual(
                first.private_attestation["bundle_root_sha256"],
                second.private_attestation["bundle_root_sha256"],
            )
            self.assertTrue(file_sha256(ledger))

    def test_rejects_scenario_spec_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario, instance = self._bundle(root)
            payload = json.loads(scenario.read_text(encoding="utf-8"))
            payload["instance_spec_sha256"] = "wrong"
            scenario.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                "canonical instance",
            ):
                build_frozen_bundle(
                    bundle_root=root,
                    scenario_path=scenario,
                    instance_spec_path=instance,
                    source_commit="abc",
                    runtime_revision="forgejo-revision",
                    salt="fixed-salt",
                )

    def test_verifier_rejects_drift_and_unbound_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario, instance = self._bundle(root)
            bundle = build_frozen_bundle(
                bundle_root=root,
                scenario_path=scenario,
                instance_spec_path=instance,
                source_commit="abc",
                runtime_revision="forgejo-revision",
                salt="fixed-salt",
                excluded_relative_paths=(
                    "freeze.json",
                    "public.json",
                    "usage-ledger.json",
                ),
            )
            freeze = root / "freeze.json"
            public = root / "public.json"
            freeze.write_text(
                json.dumps(bundle.private_attestation),
                encoding="utf-8",
            )
            public.write_text(
                json.dumps(bundle.public_commitment),
                encoding="utf-8",
            )
            (root / "usage-ledger.json").write_text(
                json.dumps({"events": []}),
                encoding="utf-8",
            )
            result = verify_frozen_bundle(
                bundle_root=root,
                private_attestation_path=freeze,
                public_commitment_path=public,
                allowed_unbound_relative_paths=("usage-ledger.json",),
            )
            self.assertTrue(result["passed"])

            (root / "undeclared.txt").write_text("drift", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "undeclared"):
                verify_frozen_bundle(
                    bundle_root=root,
                    private_attestation_path=freeze,
                    public_commitment_path=public,
                    allowed_unbound_relative_paths=("usage-ledger.json",),
                )


if __name__ == "__main__":
    unittest.main()
