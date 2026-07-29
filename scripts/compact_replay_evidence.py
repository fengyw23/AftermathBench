from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.evidence_replay import (
    project_evidence,
    replay_graph,
    replay_selectors,
)


def compact_replay_evidence(
    *,
    graph_path: Path,
    replay_path: Path,
) -> dict:
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    before = replay_graph(graph, replay)
    selectors = replay_selectors(graph)
    for capture in replay.get("captures", ()):
        capture["evidence"] = project_evidence(
            capture.get("evidence", {}),
            selectors,
        )
        capture["evidence_projection"] = {
            "selectors": list(selectors),
            "source": "minimal projection of the hashed source report",
        }
    after = replay_graph(graph, replay)
    if tuple(result.passed for result in before) != tuple(
        result.passed for result in after
    ):
        raise RuntimeError("evidence compaction changed replay outcomes")
    replay_path.write_text(
        json.dumps(replay, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "capture_count": len(replay.get("captures", ())),
        "selector_count": len(selectors),
        "relation_count": len(after),
        "all_relations_replayed": bool(after)
        and all(result.passed for result in after),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    args = parser.parse_args()
    result = compact_replay_evidence(
        graph_path=args.graph,
        replay_path=args.replay,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
