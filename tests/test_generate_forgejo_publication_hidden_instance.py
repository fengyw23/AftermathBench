from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aftermath_bench.integrations.forgejo_publication_instance import (
    ForgejoPublicationInstanceSpec,
)
from scripts.generate_forgejo_publication_hidden_instance import build_instance
from scripts.verify_forgejo_instance_novelty import (
    IDENTITY_FIELDS,
    _find_overlaps_in_corpus,
)


class GenerateForgejoPublicationHiddenInstanceTests(unittest.TestCase):
    def test_generated_instance_is_a_complete_valid_native_spec(self) -> None:
        payload = build_instance("test-001")
        instance = ForgejoPublicationInstanceSpec.from_dict(payload)

        self.assertIn("hidden-test-001-", instance.scenario_id)
        self.assertEqual(instance.owner.split("-ops")[0], instance.repository.split("-")[-1].join(["cobalt-", ""]))
        self.assertEqual(len(payload), len(ForgejoPublicationInstanceSpec.__dataclass_fields__))

    def test_each_generation_has_a_distinct_identity_surface(self) -> None:
        first = build_instance("test-001")
        second = build_instance("test-002")

        self.assertNotEqual(first["scenario_id"], second["scenario_id"])
        for field in IDENTITY_FIELDS:
            self.assertNotEqual(first[field], second[field], field)

    def test_generated_identity_does_not_overlap_a_repository_corpus(self) -> None:
        payload = build_instance("test-001")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "public.txt"
            path.write_text("ordinary public benchmark material", encoding="utf-8")
            overlaps = _find_overlaps_in_corpus(
                payload,
                [(path, path.read_text(encoding="utf-8"))],
            )

        self.assertEqual(overlaps, [])


if __name__ == "__main__":
    unittest.main()
