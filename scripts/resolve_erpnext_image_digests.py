from __future__ import annotations

import json

from aftermath_bench.integrations.image_digest import resolve_manifest_digest
from aftermath_bench.integrations.erpnext_runtime import load_runtime_lock


def main() -> int:
    lock = load_runtime_lock()
    resolved = {
        name: {
            "reference": image["reference"],
            "digest": resolve_manifest_digest(image["reference"]),
        }
        for name, image in lock["infrastructure_images"].items()
    }
    print(json.dumps(resolved, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

