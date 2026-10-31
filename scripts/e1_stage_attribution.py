"""Stage attribution for E1 control captures (issue #275, diagnosis only).

Reads pool-capturing captures (`control-pool-<case>.json`, issue #300) and, for
each case's target symbol, reports the first pipeline stage at which the target
is lost: discovery, document cap, fetch, chunk limits, byte allocation. It reads
the capture files only; it never calls a service.

    python scripts/e1_stage_attribution.py [--label control-pool]
"""

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "DOCS/evaluations/code-evidence-e1"
RAW = ROOT / "DOCS/test_results/_raw/code-evidence-e1"


def label(chunk: dict) -> str:
    metadata = chunk.get("metadata") or {}
    return str(
        chunk.get("canonical_id")
        or metadata.get("canonical_id")
        or (metadata.get("source_metadata") or {}).get("canonical_id")
        or ""
    )


def attribute(record: dict, target: str) -> dict[str, Any]:
    plan = record["response"]["retrieval_plan"]
    trace = next(
        (t for t in plan.get("evidence_trace", []) if t["canonical_id"] == target), {}
    )
    seeds = set(plan["seed_canonical_ids"])
    discovered = target in seeds | set(plan["expanded_canonical_ids"])
    pool = record["pre_budget_chunks"]
    final = record["final_chunks"]
    positions = [i for i, c in enumerate(pool) if label(c) == target]
    in_final = any(label(c) == target for c in final)
    stages = {
        "discovery": discovered,
        "document_cap": target in seeds or bool(trace.get("survives_cap")),
        "fetch": bool(trace.get("chunk_fetched")),
        "chunk_limits": bool(positions),
        "byte_allocation": in_final,
    }
    first_lost = next((name for name, ok in stages.items() if not ok), None)
    ahead = pool[: positions[0]] if positions else []
    target_bytes = [len(pool[i]["text"].encode("utf-8")) for i in positions]
    return {
        "stages": stages,
        "first_lost_stage": first_lost,
        "target_in_pool": bool(positions),
        "target_in_final": in_final,
        "target_pool_positions": positions,
        "target_chunk_bytes": target_bytes,
        "pool_size": len(pool),
        "documents_ahead_in_pool": len({c["document_id"] for c in ahead}),
        "ahead_in_pool_kinds": kinds(ahead),
        "final_kinds": kinds(final),
        "context_budget": plan["context_budget"],
        "final_slack_bytes": plan["context_budget"] - plan["tokens_after_budget"],
        "drop_reason": trace.get("drop_reason"),
    }


def kinds(chunks: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        path = label(chunk).split("#")[0]
        if path.startswith("DOCS/") or path.endswith(".md"):
            kind = "documentation"
        elif "/tests/" in path or path.startswith("tests/"):
            kind = "test"
        else:
            kind = "source"
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="control-pool")
    args = parser.parse_args()
    manifest = json.loads((DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        path = RAW / f"{args.label}-{case['id']}.json"
        if not path.exists():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        print(json.dumps({"case": case["id"], **attribute(record, case["target"])}))


if __name__ == "__main__":
    main()
