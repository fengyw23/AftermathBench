from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from aftermath_bench.integrations.kubernetes_stack import (
    KubernetesStack,
    _patch_etcd_manifest_data_path,
    _patch_etcd_manifest_snapshot_mount,
    _patch_static_pod_manifest_replay_token,
)


ETCD_MANIFEST = """\
apiVersion: v1
kind: Pod
metadata:
  name: etcd-aftermath-kubernetes-control-plane
spec:
  containers:
  - command:
    - etcd
    name: etcd
    volumeMounts:
    - mountPath: /var/lib/etcd
      name: etcd-data
    - mountPath: /etc/kubernetes/pki/etcd
      name: etcd-certs-0
  volumes:
  - hostPath:
      path: /etc/kubernetes/pki/etcd
      type: DirectoryOrCreate
    name: etcd-certs-0
  - hostPath:
      path: /var/lib/etcd
      type: DirectoryOrCreate
    name: etcd-data
"""


class KubernetesStackBundleTests(unittest.TestCase):
    def test_snapshot_mount_patch_is_complete_and_idempotent(self) -> None:
        patched = _patch_etcd_manifest_snapshot_mount(ETCD_MANIFEST)
        self.assertIn(
            "mountPath: /aftermath-etcd-bundles",
            patched,
        )
        self.assertIn(
            "path: /var/lib/aftermath-etcd-bundles",
            patched,
        )
        self.assertEqual(
            _patch_etcd_manifest_snapshot_mount(patched),
            patched,
        )

    def test_data_path_patch_changes_only_etcd_data_volume(self) -> None:
        mounted = _patch_etcd_manifest_snapshot_mount(ETCD_MANIFEST)
        restore_path = (
            "/var/lib/aftermath-etcd-bundles/restores/restore-123"
        )
        patched = _patch_etcd_manifest_data_path(mounted, restore_path)
        self.assertIn(f"path: {restore_path}", patched)
        self.assertIn("path: /etc/kubernetes/pki/etcd", patched)
        self.assertEqual(patched.count(f"path: {restore_path}"), 1)

    def test_data_path_patch_rejects_path_escape(self) -> None:
        with self.assertRaisesRegex(ValueError, "escaped"):
            _patch_etcd_manifest_data_path(
                ETCD_MANIFEST,
                "/var/lib/etcd",
            )

    def test_sqlite_snapshot_collapses_wal_into_one_database(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "live.sqlite3"
            snapshot = root / "snapshot.sqlite3"
            with closing(sqlite3.connect(source)) as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("CREATE TABLE events(key TEXT PRIMARY KEY)")
                connection.execute("INSERT INTO events VALUES ('stable')")
                connection.commit()
            KubernetesStack._snapshot_sqlite(source, snapshot)
            with closing(sqlite3.connect(snapshot)) as connection:
                self.assertEqual(
                    connection.execute("SELECT key FROM events").fetchall(),
                    [("stable",)],
                )

    def test_bundle_validation_rejects_file_drift(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            files = {
                "etcd": root / "etcd.snapshot.db",
                "external_registry": root / "webhook-sink.sqlite3",
            }
            for key, path in files.items():
                path.write_bytes(key.encode())
            manifest = {
                "schema_version": "1.0",
                "capture_mode": (
                    "etcd_snapshot_and_quiesced_registry_sqlite"
                ),
                "cluster_name": "aftermath-kubernetes",
                "node_image": "node@sha256:test",
                "files": {
                    key: {
                        "path": path.name,
                        "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                    for key, path in files.items()
                },
            }
            (root / "bundle.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            stack = KubernetesStack(
                cluster_name="aftermath-kubernetes",
                node_image="node@sha256:test",
                config=root / "kind.yaml",
            )
            stack._validated_bundle(root)
            files["etcd"].write_bytes(b"drift")
            with self.assertRaisesRegex(ValueError, "file drift: etcd"):
                stack._validated_bundle(root)

    def test_wait_for_etcd_restart_requires_a_new_container_identity(self) -> None:
        stack = KubernetesStack(
            cluster_name="aftermath-kubernetes",
            node_image="node@sha256:test",
            config=Path("kind.yaml"),
        )
        with (
            patch.object(
                KubernetesStack,
                "_etcd_container",
                side_effect=["old-etcd", "new-etcd"],
            ),
            patch.object(KubernetesStack, "_wait_api_ready") as wait_ready,
        ):
            observed = stack._wait_etcd_restarted(
                "old-etcd",
                attempts=2,
                delay_seconds=0,
            )
        self.assertEqual(observed, "new-etcd")
        wait_ready.assert_called_once_with(
            attempts=2,
            delay_seconds=0,
        )

    def test_wait_for_etcd_restart_does_not_retry_api_wait(self) -> None:
        stack = KubernetesStack(
            cluster_name="aftermath-kubernetes",
            node_image="node@sha256:test",
            config=Path("kind.yaml"),
        )
        with (
            patch.object(
                KubernetesStack,
                "_etcd_container",
                return_value="new-etcd",
            ) as container,
            patch.object(
                KubernetesStack,
                "_wait_api_ready",
                side_effect=RuntimeError("API stayed unavailable"),
            ) as wait_ready,
        ):
            with self.assertRaisesRegex(RuntimeError, "API stayed unavailable"):
                stack._wait_etcd_restarted(
                    "old-etcd",
                    attempts=2,
                    delay_seconds=0,
                )
        container.assert_called_once_with()
        wait_ready.assert_called_once_with(
            attempts=2,
            delay_seconds=0,
        )

    def test_restore_restarts_stateful_control_plane_consumers(self) -> None:
        stack = KubernetesStack(
            cluster_name="aftermath-kubernetes",
            node_image="node@sha256:test",
            config=Path("kind.yaml"),
        )
        with (
            patch.object(
                KubernetesStack,
                "_docker",
                side_effect=[
                    "apiVersion: v1\nkind: Pod\nmetadata:\n  name: manager\n",
                    "",
                    "",
                    "apiVersion: v1\nkind: Pod\nmetadata:\n  name: scheduler\n",
                    "",
                    "",
                ],
            ) as docker,
            patch.object(
                KubernetesStack,
                "_wait_control_plane_container_restarted",
                side_effect=["new-manager", "new-scheduler"],
            ) as wait_restarted,
            patch.object(KubernetesStack, "_wait_api_ready") as wait_ready,
        ):
            observed = stack._restart_control_plane_consumers(
                {
                    "kube-controller-manager": "old-manager",
                    "kube-scheduler": "old-scheduler",
                },
                attempts=2,
                delay_seconds=0,
            )
        self.assertEqual(
            observed,
            {
                "kube-controller-manager": "new-manager",
                "kube-scheduler": "new-scheduler",
            },
        )
        self.assertEqual(
            [call.args[0] for call in docker.call_args_list],
            ["exec", "cp", "exec", "exec", "cp", "exec"],
        )
        self.assertEqual(wait_restarted.call_count, 2)
        wait_ready.assert_called_once_with(
            attempts=2,
            delay_seconds=0,
        )

    def test_static_pod_replay_token_is_inserted_and_replaced(self) -> None:
        original = (
            "apiVersion: v1\n"
            "kind: Pod\n"
            "metadata:\n"
            "  labels:\n"
            "    component: kube-controller-manager\n"
            "  name: kube-controller-manager\n"
            "spec:\n"
            "  containers: []\n"
        )
        first = _patch_static_pod_manifest_replay_token(original, "a" * 32)
        second = _patch_static_pod_manifest_replay_token(first, "b" * 32)
        self.assertIn("  annotations:\n", first)
        self.assertIn(
            "    aftermathbench.dev/replay-token: " + "a" * 32,
            first,
        )
        self.assertNotIn("a" * 32, second)
        self.assertEqual(second.count("aftermathbench.dev/replay-token"), 1)

    def test_restore_rejects_incomplete_previous_consumer_identities(self) -> None:
        stack = KubernetesStack(
            cluster_name="aftermath-kubernetes",
            node_image="node@sha256:test",
            config=Path("kind.yaml"),
        )
        with self.assertRaisesRegex(ValueError, "identities are incomplete"):
            stack._restart_control_plane_consumers(
                {"kube-controller-manager": "old-manager"},
                attempts=1,
                delay_seconds=0,
            )


if __name__ == "__main__":
    unittest.main()
