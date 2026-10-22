"""Offline 4096-byte evidence-feasibility oracle for the frozen E1 cases (#264).

Oracle only: it knows the frozen witness/dependency expressions, which a
production selector does not. It measures how many final-context bytes the
essential evidence needs when delivered as (a) exact source statements,
(b) one contiguous source span per function and (c) whole stored chunks, using
the real chunker and the real ``[Source: ...]`` rendering/separators. No
network, database, model or runtime-policy change.

    ./.venv/Scripts/python.exe scripts/code_evidence_feasibility.py [--json OUT]
"""

from __future__ import annotations

import argparse
import importlib
import itertools
import json
import re
import sys
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "DOCS/evaluations/code-evidence-e1/manifest.json"
BASELINES = ROOT / "DOCS/test_results/code-evidence-e1"
sys.path.insert(0, str(ROOT))

from shared.chunkers.selector import ChunkerFactory  # noqa: E402


def _load_adapter() -> Any:
    """Import agent_adapter without running the retrieval package __init__.

    The package init builds service settings and imports HTTP clients; the
    adapter's rendering helpers need neither, and this experiment is offline.
    """
    package_dir = ROOT / "rag_orchestrator/src/retrieval"
    package = types.ModuleType("_e1_retrieval")
    package.__path__ = [str(package_dir)]  # type: ignore[attr-defined]
    sys.modules["_e1_retrieval"] = package
    return importlib.import_module("_e1_retrieval.agent_adapter")


_adapter = _load_adapter()
_render_chunk = _adapter._render_chunk
conservative_token_count = _adapter.conservative_token_count

SEPARATOR = "\n\n"  # assemble_context joins rendered parts with this


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def utf8(text: str) -> int:
    return conservative_token_count(text)


def agent_chunk(canonical_id: str, text: str) -> dict[str, Any]:
    return {"text": text, "metadata": {"canonical_id": canonical_id}}


def context_bytes(parts: list[tuple[str, str]]) -> int:
    """Exact bytes of a final context built from (canonical_id, text) parts."""
    rendered = [_render_chunk(agent_chunk(c, t)) for c, t in parts]
    return utf8(SEPARATOR.join(rendered))


def reproduce_chunks(text: str) -> tuple[str, dict[str, Any], list[str]]:
    chunker, params = ChunkerFactory.choose_strategy(text)
    strategy = getattr(chunker, "chunk_strategy", "unknown")
    return strategy, params, [c.content for c in chunker.chunk(text, **params)]


def statement_end(lines: list[str], i: int) -> int:
    depth, j = 0, i
    while j < len(lines):
        for ch in lines[j]:
            depth += ch in "([{"
            depth -= ch in ")]}"
        if depth <= 0:
            break
        j += 1
    return j


def locate_lines(lines: list[str], expr: str) -> int | None:
    first = expr.split("\n")[0].strip()
    for i, line in enumerate(lines):
        if first in line:
            return i
    # fragment spanning a line break: match on whitespace-normalised text
    target = norm(expr)
    for i in range(len(lines)):
        window = norm(" ".join(lines[i : i + 4]))
        if target in window:
            return i
    return None


def validate_chunks(sources: dict[str, Any], repro: dict[str, list[str]]) -> dict:
    """Compare reproduced chunks with stored chunk text captured in baselines."""
    checked = matched = 0
    mismatches: list[str] = []
    for path in sorted(BASELINES.glob("baseline-[LF]?.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for chunk in data["final_chunks"]:
            cid = chunk.get("canonical_id")
            if cid not in repro:
                continue
            checked += 1
            if chunk["text"] in repro[cid]:
                matched += 1
            else:
                mismatches.append(f"{path.stem}:{cid}:{chunk['chunk_index']}")
    return {"checked": checked, "matched": matched, "mismatches": mismatches}


def min_cover(options: list[set[int]], sizes: dict[tuple[str, int], int], cid: str):
    """Cheapest chunk set (by rendered size) hitting every fragment's options."""
    best: tuple[int, tuple[int, ...]] | None = None
    for pick in itertools.product(*[sorted(o) for o in options]):
        chosen = tuple(sorted(set(pick)))
        cost = sum(sizes[(cid, k)] for k in chosen)
        if best is None or cost < best[0]:
            best = (cost, chosen)
    return best


def evaluate_case(case: dict, manifest: dict, repro: dict, meta: dict) -> dict:
    cap = manifest["context_cap_bytes"]
    fragments: list[tuple[str, str, str]] = [
        (w["canonical_id"], e, kind)
        for kind, group in (("op", case["operations"]), ("dep", case["dependencies"]))
        for w in group
        for e in w["expressions"]
    ]
    by_doc: dict[str, list[tuple[str, str]]] = {}
    for cid, expr, kind in fragments:
        by_doc.setdefault(cid, []).append((expr, kind))

    exact_parts: list[tuple[str, str]] = []
    span_parts: list[tuple[str, str]] = []
    chunk_parts: list[tuple[str, str]] = []
    docs: dict[str, Any] = {}
    unlocated: list[str] = []
    chunk_selection: dict[str, list[int]] = {}
    split_fragments: list[str] = []

    for cid, items in by_doc.items():
        text = manifest["sources"][cid]["text"]
        lines = text.split("\n")
        covered: set[int] = set()
        for expr, _ in items:
            i = locate_lines(lines, expr)
            if i is None:
                unlocated.append(expr[:60])
                continue
            covered.update(range(i, statement_end(lines, i) + 1))
        ordered = sorted(covered)
        ranges: list[tuple[int, int]] = []
        for x in ordered:
            if ranges and x == ranges[-1][1] + 1:
                ranges[-1] = (ranges[-1][0], x)
            else:
                ranges.append((x, x))
        exact_parts += [(cid, "\n".join(lines[a : b + 1])) for a, b in ranges]
        if ordered:
            span_parts.append((cid, "\n".join(lines[ordered[0] : ordered[-1] + 1])))

        chunks = repro[cid]
        sizes = {
            (cid, k): utf8(_render_chunk(agent_chunk(cid, c)))
            for k, c in enumerate(chunks)
        }
        options: list[set[int]] = []
        for expr, _ in items:
            hit = {k for k, c in enumerate(chunks) if norm(expr) in norm(c)}
            if not hit:
                split_fragments.append(expr[:60])
                continue
            options.append(hit)
        best = min_cover(options, sizes, cid) if options else None
        chosen = best[1] if best else ()
        chunk_selection[cid] = list(chosen)
        chunk_parts += [(cid, chunks[k]) for k in chosen]
        window = (chosen[0], chosen[-1]) if chosen else None
        docs[cid] = {
            "source_bytes": utf8(text),
            "chunks": len(chunks),
            "strategy": meta[cid]["strategy"],
            "chunk_indices": list(chosen),
            "contiguous_window_chunks": (window[1] - window[0] + 1) if window else 0,
            "contiguous_window_bytes": (
                sum(sizes[(cid, k)] for k in range(window[0], window[1] + 1))
                if window
                else 0
            ),
        }

    result = {
        "fragments": len(fragments),
        "unlocated_fragments": unlocated,
        "fragments_split_across_chunks": split_fragments,
        "exact_statements_bytes": context_bytes(exact_parts),
        "exact_statements_parts": len(exact_parts),
        "contiguous_span_bytes": context_bytes(span_parts),
        "whole_chunk_bytes": context_bytes(chunk_parts),
        "whole_chunk_count": len(chunk_parts),
        "docs": docs,
    }
    result["window_chunks_total"] = sum(
        d["contiguous_window_chunks"] for d in docs.values()
    )
    result["contiguous_window_bytes"] = sum(
        d["contiguous_window_bytes"] for d in docs.values()
    ) + len(SEPARATOR) * max(result["window_chunks_total"] - 1, 0)
    result["fits"] = {
        "exact_statements": result["exact_statements_bytes"] <= cap,
        "contiguous_span": result["contiguous_span_bytes"] <= cap,
        "whole_chunks": result["whole_chunk_bytes"] <= cap,
        "contiguous_windows": result["contiguous_window_bytes"] <= cap,
    }
    # prototype-contract limits: <=3 documents, one window of <=5 chunks each
    result["passage_only_contract_window_ok"] = all(
        d["contiguous_window_chunks"] <= 5 for d in docs.values()
    ) and len(docs) <= 3
    result["passage_only_contract_feasible"] = bool(
        result["passage_only_contract_window_ok"]
        and result["fits"]["contiguous_windows"]
    )
    return result


def run() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    repro: dict[str, list[str]] = {}
    meta: dict[str, Any] = {}
    faithful: dict[str, Any] = {}
    for cid, source in manifest["sources"].items():
        strategy, params, chunks = reproduce_chunks(source["text"])
        repro[cid] = chunks
        meta[cid] = {"strategy": strategy, "params": params}
        text = source["text"]
        faithful[cid] = {
            "chunks": len(chunks),
            "chunks_not_verbatim_source": sum(1 for c in chunks if c not in text),
            "max_chunk_chars": max(len(c) for c in chunks),
        }
    cases = {
        c["id"]: evaluate_case(c, manifest, repro, meta) for c in manifest["cases"]
    }
    return {
        "cap_bytes": manifest["context_cap_bytes"],
        "chunker_validation": validate_chunks(manifest["sources"], repro),
        "chunk_faithfulness": faithful,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write full results JSON here")
    args = parser.parse_args()
    out = run()
    v = out["chunker_validation"]
    print(f"chunker reproduction: {v['matched']}/{v['checked']} stored chunks match")
    for cid, f in out["chunk_faithfulness"].items():
        print(f"  {cid}: {f}")
    print(f"cap={out['cap_bytes']}")
    print(
        "case exact(B) span(B) chunks(B,n) windows(B,n)  "
        "fits(exact/span/chunks/windows) contract"
    )
    for cid, r in out["cases"].items():
        f = r["fits"]
        print(
            f"{cid:4} {r['exact_statements_bytes']:6} {r['contiguous_span_bytes']:6} "
            f"{r['whole_chunk_bytes']:6},{r['whole_chunk_count']:<2} "
            f"{r['contiguous_window_bytes']:6},{r['window_chunks_total']:<2} "
            f"{f['exact_statements']}/{f['contiguous_span']}/{f['whole_chunks']}/"
            f"{f['contiguous_windows']} contract={r['passage_only_contract_feasible']} "
            f"unlocated={len(r['unlocated_fragments'])} "
            f"split={len(r['fragments_split_across_chunks'])}"
        )
    if args.json:
        args.json.write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
