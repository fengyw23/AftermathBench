import json
import unittest

from aftermath_bench.schema import repository_root


class ERPNextComposeSpecTest(unittest.TestCase):
    def setUp(self) -> None:
        runtime = repository_root() / "runtimes" / "erpnext"
        self.compose = (runtime / "compose.yaml").read_text(encoding="utf-8")
        self.lock = json.loads(
            (runtime / "runtime.lock.json").read_text(encoding="utf-8")
        )

    def test_native_state_and_fault_services_are_present(self) -> None:
        for service in (
            "db:",
            "redis-queue:",
            "queue-fault:",
            "backend:",
            "queue-short:",
            "queue-long:",
            "fault-gateway:",
            "remittance:",
        ):
            self.assertIn(service, self.compose)

    def test_erpnext_application_image_is_local_source_build(self) -> None:
        self.assertIn("aftermathbench/erpnext:v15.118.1", self.compose)
        self.assertIn("pull_policy: never", self.compose)

    def test_site_creation_does_not_depend_on_missing_wait_helper(self) -> None:
        self.assertNotIn("wait-for-it", self.compose)

    def test_site_creation_is_one_atomic_shell_command(self) -> None:
        command = next(
            line.strip()
            for line in self.compose.splitlines()
            if line.strip().startswith("bench new-site aftermath.localhost")
        )
        for option in (
            "--mariadb-user-host-login-scope='%'",
            '--admin-password="$${AFTERMATH_ADMIN_PASSWORD}"',
            "--db-root-username=root",
            '--db-root-password="$${AFTERMATH_DB_ROOT_PASSWORD}"',
            "--install-app erpnext",
            "--set-default;",
        ):
            self.assertIn(option, command)

    def test_direct_runtime_images_are_digest_pinned(self) -> None:
        images = self.lock["infrastructure_images"]
        self.assertTrue(
            all(
                str(image["digest"]).startswith("sha256:")
                for image in images.values()
            )
        )
        for image in images.values():
            self.assertIn(image["digest"], self.compose + (
                repository_root()
                / "runtimes"
                / "erpnext"
                / "control"
                / "Containerfile"
            ).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
