from __future__ import annotations

import json
import unittest
from pathlib import Path


class KubernetesSnapshotReplayWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).parents[1]
        cls.text = (
            cls.root
            / ".github"
            / "workflows"
            / "kubernetes-snapshot-replay-proof.yml"
        ).read_text(encoding="utf-8")
        cls.lock = json.loads(
            (cls.root / "runtimes" / "kubernetes" / "runtime.lock.json")
            .read_text(encoding="utf-8")
        )

    def test_snapshot_mount_is_installed_before_boundary(self) -> None:
        prepare = self.text.index("prepare-snapshot-runtime")
        boundary = self.text.index("run_kubernetes_interaction_boundary.py")
        proof = self.text.rindex("verify_kubernetes_snapshot_replay.py")
        self.assertLess(prepare, boundary)
        self.assertLess(boundary, proof)

    def test_registry_uses_a_durable_bind_mount_and_is_not_auto_removed(self) -> None:
        self.assertIn('--mount "type=bind,src=$registry_root,dst=/data"', self.text)
        self.assertIn('sudo chown 65532:65532 "$registry_root"', self.text)
        self.assertIn("docker logs aftermath-interaction-registry", self.text)
        registry_section = self.text[
            self.text.index("docker run --detach") : self.text.index(
                "Install exact-replay mount"
            )
        ]
        self.assertNotIn("--rm", registry_section)

    def test_sensitive_snapshot_is_not_uploaded(self) -> None:
        upload = self.text[self.text.index("Upload safe replay proof") :]
        self.assertIn("k0-evidence", upload)
        self.assertNotIn("k0-sensitive/", upload)
        self.assertIn('sudo chown -R "$(id -u):$(id -g)"', upload)

    def test_proof_has_no_model_provider_or_secret(self) -> None:
        lowered = self.text.lower()
        for forbidden in (
            "api_key",
            "api-key",
            "zhipu",
            "deepseek",
            "openai",
            "run-native-model",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_etcdutl_archive_and_digest_match_runtime_lock(self) -> None:
        self.assertIn(self.lock["etcd"]["url"], self.text)
        self.assertIn(self.lock["etcd"]["sha256"], self.text)
        self.assertIn('"$RUNNER_TEMP/bin/etcdutl"', self.text)


if __name__ == "__main__":
    unittest.main()
