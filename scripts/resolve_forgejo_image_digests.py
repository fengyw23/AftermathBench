from __future__ import annotations

import json

from aftermath_bench.integrations.forgejo_runtime import default_lock_path
from aftermath_bench.integrations.image_digest import resolve_manifest_digest


def main() -> int:
    lock = json.loads(default_lock_path().read_text(encoding="utf-8"))
    resolved = {
        name: {
            "reference": image["reference"],
            "recorded_digest": image["digest"],
            "resolved_digest": resolve_manifest_digest(image["reference"]),
        }
        for name, image in lock["base_images"].items()
    }
    for item in resolved.values():
        item["matches"] = (
            item["recorded_digest"] == item["resolved_digest"]
        )
    print(json.dumps(resolved, indent=2))
    return 0 if all(item["matches"] for item in resolved.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
