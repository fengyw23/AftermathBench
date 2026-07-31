from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from aftermath_bench.forgejo_publication_state_evidence import (
    ForgejoPublicationStateEvidenceError,
    bind_exact_bundle,
    capture_forgejo_publication_state_evidence,
    deterministic_state_projection,
    establish_expected_projection,
    write_state_evidence,
)


class _Environment:
    def __init__(self, state: dict):
        self.state = deepcopy(state)

    def snapshot_metadata(self) -> dict:
        return deepcopy(self.state)

    def snapshot(self) -> dict:
        raise AssertionError(
            "formal state capture must not use the downloading snapshot"
        )


class ForgejoPublicationStateEvidenceTests(unittest.TestCase):
    variant = "release_committed_both_delivered"
    scenario_id = "forgejo-state-evidence-test"
    instance_sha256 = "1" * 64

    @staticmethod
    def _write_json(path: Path, payload: object) -> bytes:
        raw = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return raw

    def _inputs(self, root: Path) -> dict[str, Path]:
        credentials = root / "credentials.json"
        prefix = root / "prefix.json"
        self._write_json(
            credentials,
            {
                "base_url": "http://forgejo.invalid/api/v1",
                "token": "secret",
                "web_base_url": "http://forgejo.invalid",
                "username": "owner",
                "password": "password",
            },
        )
        self._write_json(
            prefix,
            {
                "scenario_id": self.scenario_id,
                "instance_spec_sha256": self.instance_sha256,
                "owner": "owner",
                "repository": "repository",
                "release_tag": "v9.8.7",
            },
        )
        bundle = root / "bundle"
        bundle.mkdir()
        forgejo = bundle / "forgejo-data.tar.gz"
        sink = bundle / "webhook-sink-data.tar.gz"
        manifest = bundle / "bundle.json"
        asset_uuid = "01234567-89ab-4def-8123-456789abcdef"
        asset_content = b"exact attachment data"
        with tarfile.open(forgejo, mode="w:gz") as archive:
            member = tarfile.TarInfo(
                "./gitea/attachments/0/1/" + asset_uuid
            )
            member.size = len(asset_content)
            archive.addfile(member, io.BytesIO(asset_content))
        sink.write_bytes(b"exact receiver archive")
        self._write_json(
            manifest,
            {
                "schema_version": "1.0",
                "capture_mode": "simultaneous_service_quiescence",
                "forgejo_sha256": hashlib.sha256(forgejo.read_bytes()).hexdigest(),
                "webhook_sink_sha256": hashlib.sha256(sink.read_bytes()).hexdigest(),
            },
        )
        return {
            "credentials": credentials,
            "prefix": prefix,
            "manifest": manifest,
            "forgejo": forgejo,
            "sink": sink,
        }

    @staticmethod
    def _state() -> dict:
        release = {
            "id": 91,
            "tag_name": "v9.8.7",
            "target_commitish": "release/9.8",
        }
        asset = {
            "id": 201,
            "name": "package.tar.gz",
            "size": 21,
            "uuid": "01234567-89ab-4def-8123-456789abcdef",
            "browser_download_url": (
                "http://forgejo.invalid/attachments/"
                "01234567-89ab-4def-8123-456789abcdef"
            ),
            "content_sha256": hashlib.sha256(
                b"exact attachment data"
            ).hexdigest(),
            "content_size": 21,
        }
        coordinator = {"uuid": "delivery-a", "status": "succeeded"}
        provenance = {"uuid": "delivery-b", "status": "succeeded"}
        deliveries = [
            {
                "key": "delivery-b",
                "attempt_count": 1,
                "payload": {"release": {"tag_name": "v9.8.7"}},
            },
            {
                "key": "delivery-a",
                "attempt_count": 1,
                "payload": {"release": {"tag_name": "v9.8.7"}},
            },
        ]
        return {
            "releases": [release],
            "target_release_assets": [asset],
            "coordinator_history": [coordinator],
            "provenance_history": [provenance],
            "external_deliveries": deliveries,
            "target_pull": {"index": 7, "state": "closed"},
            "linked_issue": {"index": 6, "state": "closed"},
            "release_milestone": {"id": 5, "state": "open"},
            "base_branch": {"name": "release/9.8"},
            "protected_release_assets": [],
            "protected_pull": {"index": 8, "state": "open"},
            "protected_issue": {"index": 9, "state": "open"},
            "branch_protections": [{"rule_name": "release/**"}],
            "hooks": [{"id": 3}, {"id": 2}],
            "opaque_native_record": {
                "retained_without_field_selection": True,
            },
        }

    def _capture_reset(
        self,
        root: Path,
        *,
        state: dict | None = None,
        expected: object | None = None,
    ) -> tuple[dict, dict[str, Path]]:
        inputs = self._inputs(root)
        current_state = state or self._state()
        expected_path = None
        if expected is not None:
            expected_path = root / "expected.json"
            self._write_json(expected_path, expected)
        payload = capture_forgejo_publication_state_evidence(
            phase="reset",
            credentials_path=inputs["credentials"],
            prefix_path=inputs["prefix"],
            variant_id=self.variant,
            bundle_manifest_path=inputs["manifest"],
            forgejo_archive_path=inputs["forgejo"],
            webhook_sink_archive_path=inputs["sink"],
            expected_projection_path=expected_path,
            environment_factory=lambda _credentials, _prefix: _Environment(
                current_state
            ),
        )
        return payload, inputs

    def _failure_report(self, state: dict) -> dict:
        assets = [
            {
                key: value
                for key, value in asset.items()
                if key not in {"content_sha256", "content_size"}
            }
            for asset in state["target_release_assets"]
        ]
        return {
            "schema_version": "0.2",
            "scenario_id": self.scenario_id,
            "instance_spec_sha256": self.instance_sha256,
            "variant": self.variant,
            "surface_result": (
                "HTTP connection lost before publication completion was acknowledged"
            ),
            "visible_failure": {
                "ok": False,
                "error": (
                    "HTTP connection lost before publication completion "
                    "was acknowledged"
                ),
            },
            "harness_error_type": "RemoteDisconnected",
            "failure_boundary_evidence": {
                "release": state["releases"][0],
                "assets": assets,
                "coordinator_history": state["coordinator_history"],
                "provenance_history": state["provenance_history"],
                "external_deliveries": state["external_deliveries"],
            },
            "checks": {
                "surface_error_observed": True,
                "release_commit_matches_variant": True,
            },
            "passed": True,
        }

    def test_reset_binds_raw_bundle_and_is_deterministic(self) -> None:
        state = self._state()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload, inputs = self._capture_reset(
                root,
                state=state,
                expected=deterministic_state_projection(state),
            )

            first = root / "first.json"
            second = root / "second.json"
            write_state_evidence(first, payload)
            write_state_evidence(second, payload)

            self.assertTrue(payload["reset_verified"])
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(
                payload["bundle_manifest_file_sha256"],
                hashlib.sha256(inputs["manifest"].read_bytes()).hexdigest(),
            )
            self.assertEqual(
                payload["bundle"]["forgejo_archive"]["sha256"],
                hashlib.sha256(inputs["forgejo"].read_bytes()).hexdigest(),
            )
            self.assertTrue(
                payload["state_projection"]["opaque_native_record"][
                    "retained_without_field_selection"
                ]
            )
            self.assertNotIn("secret", first.read_text(encoding="utf-8"))

    def test_projection_preserves_native_array_order(self) -> None:
        state = self._state()
        projection = deterministic_state_projection(state)

        self.assertEqual(
            [delivery["key"] for delivery in projection["external_deliveries"]],
            ["delivery-b", "delivery-a"],
        )
        self.assertEqual(
            [hook["id"] for hook in projection["hooks"]],
            [3, 2],
        )

    def test_establishes_expected_projection_atomically_without_credentials(
        self,
    ) -> None:
        state = self._state()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reset, _ = self._capture_reset(root, state=state)
            projection_path = root / "expected-projection.json"

            record = establish_expected_projection(
                projection_path,
                reset,
            )
            record_path = root / "establishment-record.json"
            write_state_evidence(record_path, record)

            self.assertFalse(record["reset_verified"])
            self.assertTrue(record["expected_projection_establishment"]["performed"])
            self.assertEqual(
                json.loads(projection_path.read_text(encoding="utf-8")),
                deterministic_state_projection(state),
            )
            projection_sha256 = hashlib.sha256(projection_path.read_bytes()).hexdigest()
            self.assertEqual(
                record["expected_projection_establishment"]["file_sha256"],
                projection_sha256,
            )
            self.assertNotIn(
                "secret",
                projection_path.read_text(encoding="utf-8"),
            )
            self.assertNotIn(
                "secret",
                record_path.read_text(encoding="utf-8"),
            )
            with self.assertRaisesRegex(
                ForgejoPublicationStateEvidenceError,
                "already exists",
            ):
                establish_expected_projection(projection_path, reset)

    def test_expected_projection_and_establishment_are_mutually_exclusive(
        self,
    ) -> None:
        state = self._state()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._inputs(root)
            expected = root / "expected.json"
            self._write_json(
                expected,
                deterministic_state_projection(state),
            )

            with self.assertRaisesRegex(
                ForgejoPublicationStateEvidenceError,
                "mutually exclusive",
            ):
                capture_forgejo_publication_state_evidence(
                    phase="reset",
                    credentials_path=inputs["credentials"],
                    prefix_path=inputs["prefix"],
                    variant_id=self.variant,
                    bundle_manifest_path=inputs["manifest"],
                    forgejo_archive_path=inputs["forgejo"],
                    webhook_sink_archive_path=inputs["sink"],
                    expected_projection_path=expected,
                    establish_expected_projection=True,
                    environment_factory=(
                        lambda _credentials, _prefix: _Environment(state)
                    ),
                )

    def test_reset_is_not_verified_without_an_exact_expected_projection(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            absent, _ = self._capture_reset(root / "absent")
            mismatch, _ = self._capture_reset(
                root / "mismatch",
                expected={"not": "the complete native state"},
            )

            self.assertFalse(absent["reset_verified"])
            self.assertIsNone(absent["expected_projection"]["exact_match"])
            self.assertFalse(mismatch["reset_verified"])
            self.assertFalse(mismatch["expected_projection"]["exact_match"])

    def test_bundle_archive_bytes_must_match_bundle_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self._inputs(root)
            inputs["forgejo"].write_bytes(b"tampered")

            with self.assertRaisesRegex(
                ForgejoPublicationStateEvidenceError,
                "does not match bundle.json",
            ):
                bind_exact_bundle(
                    manifest_path=inputs["manifest"],
                    forgejo_archive_path=inputs["forgejo"],
                    webhook_sink_archive_path=inputs["sink"],
                )

    def test_boundary_binds_reset_failure_bundle_and_complete_state(
        self,
    ) -> None:
        state = self._state()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reset, inputs = self._capture_reset(
                root,
                state=state,
                expected=deterministic_state_projection(state),
            )
            reset_path = root / "reset.json"
            write_state_evidence(reset_path, reset)
            failure_path = root / "failure.json"
            self._write_json(
                failure_path,
                self._failure_report(state),
            )

            boundary = capture_forgejo_publication_state_evidence(
                phase="boundary",
                credentials_path=inputs["credentials"],
                prefix_path=inputs["prefix"],
                variant_id=self.variant,
                bundle_manifest_path=inputs["manifest"],
                forgejo_archive_path=inputs["forgejo"],
                webhook_sink_archive_path=inputs["sink"],
                reset_evidence_path=reset_path,
                failure_report_path=failure_path,
                environment_factory=(lambda _credentials, _prefix: _Environment(state)),
            )

            self.assertEqual(boundary["phase"], "boundary")
            self.assertTrue(boundary["boundary_validation_passed"])
            self.assertEqual(
                boundary["reset_snapshot_sha256"],
                hashlib.sha256(reset_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                boundary["failure_report_file_sha256"],
                hashlib.sha256(failure_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                boundary["state_projection"],
                reset["state_projection"],
            )

    def test_boundary_rejects_bad_identity_status_error_or_state(self) -> None:
        state = self._state()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reset, inputs = self._capture_reset(
                root,
                state=state,
                expected=deterministic_state_projection(state),
            )
            reset_path = root / "reset.json"
            write_state_evidence(reset_path, reset)
            cases = {
                "identity": ("scenario_id", "different-scenario"),
                "variant": (
                    "variant",
                    "release_request_not_reached",
                ),
                "status": ("passed", False),
                "error": ("visible_failure", {"ok": False, "error": ""}),
            }
            for name, (field, value) in cases.items():
                with self.subTest(name=name):
                    report = self._failure_report(state)
                    report[field] = value
                    failure = root / f"failure-{name}.json"
                    self._write_json(failure, report)
                    with self.assertRaises(ForgejoPublicationStateEvidenceError):
                        capture_forgejo_publication_state_evidence(
                            phase="boundary",
                            credentials_path=inputs["credentials"],
                            prefix_path=inputs["prefix"],
                            variant_id=self.variant,
                            bundle_manifest_path=inputs["manifest"],
                            forgejo_archive_path=inputs["forgejo"],
                            webhook_sink_archive_path=inputs["sink"],
                            reset_evidence_path=reset_path,
                            failure_report_path=failure,
                            environment_factory=(
                                lambda _credentials, _prefix: _Environment(state)
                            ),
                        )

            changed_state = deepcopy(state)
            changed_state["external_deliveries"] = []
            failure = root / "failure-state-mismatch.json"
            self._write_json(failure, self._failure_report(state))
            with self.assertRaisesRegex(
                ForgejoPublicationStateEvidenceError,
                "does not describe the captured native state",
            ):
                capture_forgejo_publication_state_evidence(
                    phase="boundary",
                    credentials_path=inputs["credentials"],
                    prefix_path=inputs["prefix"],
                    variant_id=self.variant,
                    bundle_manifest_path=inputs["manifest"],
                    forgejo_archive_path=inputs["forgejo"],
                    webhook_sink_archive_path=inputs["sink"],
                    reset_evidence_path=reset_path,
                    failure_report_path=failure,
                    environment_factory=(
                        lambda _credentials, _prefix: _Environment(changed_state)
                    ),
                )

    def test_boundary_requires_release_embedded_assets_to_be_fresh(self) -> None:
        state = self._state()
        embedded_asset = {
            key: value
            for key, value in state["target_release_assets"][0].items()
            if key not in {"content_sha256", "content_size"}
        }
        state["releases"][0]["assets"] = [embedded_asset]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reset, inputs = self._capture_reset(
                root,
                state=state,
                expected=deterministic_state_projection(state),
            )
            reset_path = root / "reset.json"
            write_state_evidence(reset_path, reset)

            fresh_report = self._failure_report(state)
            fresh_path = root / "failure-fresh-release.json"
            self._write_json(fresh_path, fresh_report)
            boundary = capture_forgejo_publication_state_evidence(
                phase="boundary",
                credentials_path=inputs["credentials"],
                prefix_path=inputs["prefix"],
                variant_id=self.variant,
                bundle_manifest_path=inputs["manifest"],
                forgejo_archive_path=inputs["forgejo"],
                webhook_sink_archive_path=inputs["sink"],
                reset_evidence_path=reset_path,
                failure_report_path=fresh_path,
                environment_factory=(
                    lambda _credentials, _prefix: _Environment(state)
                ),
            )
            self.assertTrue(boundary["boundary_validation_passed"])

            stale_report = deepcopy(fresh_report)
            stale_report["failure_boundary_evidence"]["release"]["assets"] = []
            stale_path = root / "failure-stale-release.json"
            self._write_json(stale_path, stale_report)
            with self.assertRaisesRegex(
                ForgejoPublicationStateEvidenceError,
                "captured native state: release",
            ):
                capture_forgejo_publication_state_evidence(
                    phase="boundary",
                    credentials_path=inputs["credentials"],
                    prefix_path=inputs["prefix"],
                    variant_id=self.variant,
                    bundle_manifest_path=inputs["manifest"],
                    forgejo_archive_path=inputs["forgejo"],
                    webhook_sink_archive_path=inputs["sink"],
                    reset_evidence_path=reset_path,
                    failure_report_path=stale_path,
                    environment_factory=(
                        lambda _credentials, _prefix: _Environment(state)
                    ),
                )

    def test_output_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.json"
            write_state_evidence(output, {"phase": "reset"})
            with self.assertRaisesRegex(
                ForgejoPublicationStateEvidenceError,
                "already exists",
            ):
                write_state_evidence(output, {"phase": "boundary"})


if __name__ == "__main__":
    unittest.main()
