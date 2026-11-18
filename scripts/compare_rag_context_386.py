"""Replay frozen #345 passage order against ordinary RAG byte ceilings (offline)."""

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "DOCS/evaluations/inference-pilot-345/mixed-docs-first-v1.txt"


def implementations(rows):
    return sum(not c["document_id"].startswith("DOCS/") for c in rows)


def compare():
    sys.path.insert(0, str(ROOT / "rag_orchestrator"))
    from src.retrieval.agent_adapter import assemble_context

    chunks = []
    for block in re.split(
        r"\n\n(?=\[Source: )", SOURCE.read_text(encoding="utf8").strip()
    ):
        label, text = block.split("]\n", 1)
        chunks.append(
            {
                "document_id": label.removeprefix("[Source: "),
                "chunk_id": len(chunks),
                "text": text,
            }
        )
    for case, candidates in [("mixed", chunks), ("discovery_miss", chunks[:4])]:
        for budget in (2048, 4096, 8192):
            result = assemble_context(candidates, budget)

            yield {
                "case": case,
                "ceiling_bytes": budget,
                "delivered_bytes": result.token_count,
                "implementation_candidates": implementations(candidates),
                "implementation_delivered": implementations(result.chunks),
                "omitted": len(result.omitted),
            }


if __name__ == "__main__":
    print(json.dumps(list(compare()), indent=2))
