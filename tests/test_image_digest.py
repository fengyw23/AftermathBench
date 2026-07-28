import unittest

from aftermath_bench.integrations.image_digest import (
    _bearer_parameters,
    parse_reference,
)


class ImageDigestTest(unittest.TestCase):
    def test_docker_hub_library_reference(self) -> None:
        parsed = parse_reference("mariadb:10.6.22")
        self.assertEqual(parsed.registry, "registry-1.docker.io")
        self.assertEqual(parsed.repository, "library/mariadb")
        self.assertEqual(parsed.tag, "10.6.22")

    def test_ghcr_reference(self) -> None:
        parsed = parse_reference("ghcr.io/shopify/toxiproxy:2.12.0")
        self.assertEqual(parsed.registry, "ghcr.io")
        self.assertEqual(parsed.repository, "shopify/toxiproxy")

    def test_bearer_challenge_parser(self) -> None:
        parameters = _bearer_parameters(
            'Bearer realm="https://auth.example/token",'
            'service="registry.example",scope="repository:a/b:pull"'
        )
        self.assertEqual(parameters["service"], "registry.example")
        self.assertEqual(parameters["scope"], "repository:a/b:pull")


if __name__ == "__main__":
    unittest.main()
