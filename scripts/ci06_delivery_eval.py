"""CI-06 (#337) bounded delivery evaluation, as pre-registered in
DOCS/evaluations/2026-11-10-ci06-delivery-evaluation-protocol.md.

Development data only. Compares the legacy embedding contract with ADR-056 on
discovery, statement survival through the production context assembly,
multilingual documentation needles and long queries. Embeddings come from an
Ollama serving mxbai-embed-large and are cached by input hash.

    ./.venv/Scripts/python.exe scripts/ci06_delivery_eval.py \\
      --lightrag <LightRAG@4d0afc1> --foundry-e1 <foundry@109f12d8> \\
      --foundry-r4 <foundry@3ba6a2f> --ollama "$OLLAMA_URL" \\
      --cache-dir DOCS/test_results/_raw/ci06 --json OUT.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import random
import re
import sys
import types
from collections import defaultdict
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import ci06_embedding_coverage as cov  # noqa: E402
from shared.chunkers.text import split_for_overflow  # noqa: E402

E1 = ROOT / "DOCS/evaluations/code-evidence-e1/manifest.json"
WP_R4 = ROOT / "DOCS/evaluations/wp-r4-questions.json"
SEED = 337
DISTRACTORS = 600
TOP_K = 20
SEED_PASSAGES_PER_DOC = 5
CONTEXT_BYTES = 4096
MAX_TOTAL_CHUNKS = 50
CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")


def _load_adapter():
    """Import agent_adapter without the retrieval package __init__."""
    package_dir = ROOT / "rag_orchestrator/src/retrieval"
    package = types.ModuleType("_ci06_retrieval")
    package.__path__ = [str(package_dir)]  # type: ignore[attr-defined]
    sys.modules["_ci06_retrieval"] = package
    return importlib.import_module("_ci06_retrieval.agent_adapter")


assemble_context = _load_adapter().assemble_context


def norm(text: str) -> str:
    return cov.WS.sub("", text)


# --------------------------------------------------------------------------
# Passages per contract: (canonical_id, relative_path, delivered, embedded)
# --------------------------------------------------------------------------
Passage = tuple[str, str, str, str]


class Index:
    def __init__(self, emb: cov.Embeddings):
        self.emb = emb

    def strict_fit(self, texts: list[str]) -> dict[str, list[str]]:
        """Map each text to the exact pieces the model accepts (pipeline split)."""
        self.emb.ensure(texts, label="fit")
        out: dict[str, list[str]] = {}
        for text in texts:
            if self.emb.key(text) not in self.emb.overflow:
                out[text] = [text]
                continue
            pieces = split_for_overflow(text)
            out[text] = [p for piece in pieces for p in self.strict_fit([piece])[piece]]
        return out

    def legacy(self, arts: list[cov.Artifact]) -> list[Passage]:
        rows = []
        for a in arts:
            for unit in cov._legacy_units(a.text)[1]:
                rows.append((a.canonical_id, a.relative_path, unit,
                             cov._legacy_truncate(unit)))
        # Legacy relied on Ollama's default server truncation for overflow;
        # Embeddings.ensure falls back to exactly that.
        self.emb.ensure([r[3] for r in rows], label="legacy", server_truncate=True)
        return rows

    def fitted(self, arts: list[cov.Artifact], fn: Callable) -> list[Passage]:
        units = [(a, u) for a in arts for u in fn(a.text)[2]]
        fit = self.strict_fit([u for _, u in units])
        return [
            (a.canonical_id, a.relative_path, piece, piece)
            for a, u in units for piece in fit[u]
        ]


def ranked(emb: cov.Embeddings, passages: list[Passage], query_input: str):
    qv = cov._unit(emb.vec(query_input))
    scored = [
        (cov._dot(qv, cov._unit(emb.vec(p[3]))), i) for i, p in enumerate(passages)
    ]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored


def legacy_query(text: str) -> str:
    return cov._legacy_truncate(text)


# --------------------------------------------------------------------------
# Delivery simulation
# --------------------------------------------------------------------------
def deliver(passages: list[Passage], scored, named: list[str], k_expanded: int):
    score_of = {i: s for s, i in scored}
    order: list[str] = []
    seed_passages: dict[str, list[int]] = defaultdict(list)
    for _, i in scored[:TOP_K]:
        cid = passages[i][0]
        if cid not in seed_passages:
            order.append(cid)
        if len(seed_passages[cid]) < SEED_PASSAGES_PER_DOC:
            seed_passages[cid].append(i)
    by_artifact: dict[str, list[int]] = defaultdict(list)
    for i, p in enumerate(passages):
        by_artifact[p[0]].append(i)
    chosen: list[int] = []
    for cid in order:
        chosen.extend(sorted(seed_passages[cid], key=lambda i: (-score_of[i], i)))
    for cid in named:
        if cid in seed_passages:
            continue
        best = sorted(by_artifact.get(cid, []), key=lambda i: (-score_of[i], i))
        chosen.extend(best[:k_expanded])
    chunks = [
        {"text": passages[i][2], "metadata": {"canonical_id": passages[i][0]},
         "document_id": passages[i][0], "chunk_id": str(i), "path": passages[i][1]}
        for i in chosen[:MAX_TOTAL_CHUNKS]
    ]
    context = assemble_context(chunks, CONTEXT_BYTES)
    return context.chunks, context.token_count


def credited(selected, expectations: list[tuple[str, set[str]]]) -> list[bool]:
    by_path: dict[str, str] = defaultdict(str)
    for chunk in selected:
        by_path[chunk["path"]] += norm(str(chunk["text"])) + "\0"
    return [
        any(norm(expr) in by_path[path] for path in paths)
        for expr, paths in expectations
    ]


# --------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------
def e1_cases(repo: str) -> list[dict]:
    manifest = json.loads(E1.read_text(encoding="utf-8"))
    out = []
    for case in manifest["cases"]:
        if case["repo"] != repo:
            continue
        expectations, named = [], [case["target"]]
        for group in case["operations"] + case["dependencies"]:
            named.append(group["canonical_id"])
            path = group["canonical_id"].split("#")[0]
            expectations += [(e, {path}) for e in group["expressions"]]
        out.append({"id": case["id"], "query": case["query"],
                    "target": case["target"], "named": list(dict.fromkeys(named)),
                    "expectations": expectations})
    return out


def r4_cases() -> list[dict]:
    data = json.loads(WP_R4.read_text(encoding="utf-8"))
    out = []
    for q in data["questions"]:
        paths = {c.split("#")[0] for c in q["canonical_ids"]}
        out.append({"id": f"R4-{q['id']}", "query": q["query"],
                    "target": q["canonical_ids"][0], "named": q["canonical_ids"],
                    "expectations": [(s, paths) for s in q["required_substrings"]]})
    return out


def frozen_targets(arts: list[cov.Artifact]) -> tuple[list[cov.Artifact], list[dict]]:
    """Substitute E1 frozen bodies where the extracted text differs."""
    sources = json.loads(E1.read_text(encoding="utf-8"))["sources"]
    checks, out = [], []
    for a in arts:
        src = sources.get(a.canonical_id)
        if src is None:
            out.append(a)
            continue
        match = hashlib.sha256(a.text.encode()).hexdigest() == src["sha256"]
        checks.append({"canonical_id": a.canonical_id, "extracted_matches": match})
        out.append(a if match else cov.Artifact(
            a.canonical_id, a.doc_type, a.relative_path, src["text"]))
    return out, checks


def corpus_for(arts: list[cov.Artifact], cases: list[dict]) -> list[cov.Artifact]:
    named = {c for case in cases for c in case["named"]}
    keep = [a for a in arts if a.canonical_id in named]
    missing = named - {a.canonical_id for a in keep}
    if missing:
        raise SystemExit(f"named artifacts missing from snapshot: {sorted(missing)}")
    rest = sorted((a for a in arts if a.is_code and a.canonical_id not in named),
                  key=lambda a: a.canonical_id)
    return keep + random.Random(SEED).sample(rest, min(DISTRACTORS, len(rest)))


def long_query(case: dict, arts: list[cov.Artifact]) -> str:
    path = case["target"].split("#")[0]
    module = next((a for a in arts if a.canonical_id == path), None)
    target = next(a for a in arts if a.canonical_id == case["target"])
    context = ""
    if module and target.text in module.text:
        context = module.text[: module.text.index(target.text)][-1600:]
    return f"{case['query']}\n\nRelevant file context:\n{context}"


# --------------------------------------------------------------------------
def run_snapshot(name: str, repo: Path, cases: list[dict], idx: Index) -> dict:
    arts = cov.load_artifacts(repo)
    arts, checks = frozen_targets(arts)
    corpus = corpus_for(arts, cases)
    emb = idx.emb
    indexes = {
        "legacy": idx.legacy(corpus),
        "new": idx.fitted(corpus, cov.factory("code")),
    }
    rows = []
    for case in cases:
        queries = {"short": case["query"], "long": long_query(case, arts)}
        inputs = [legacy_query(q) for q in queries.values()] + list(queries.values())
        emb.ensure(inputs, label=f"queries {case['id']}")
        row: dict = {"id": case["id"], "expected": len(case["expectations"])}
        for label, passages in indexes.items():
            q_input = (
                legacy_query(case["query"]) if label == "legacy" else case["query"]
            )
            scored = ranked(emb, passages, q_input)
            top = {passages[i][0] for _, i in scored[:TOP_K]}
            row[f"{label}_discovered"] = case["target"] in top
            for k in (3, 5):
                selected, used = deliver(passages, scored, case["named"], k)
                hits = credited(selected, case["expectations"])
                row[f"{label}_k{k}_delivered"] = sum(hits)
                row[f"{label}_k{k}_bytes"] = used
                row[f"{label}_k{k}_missing"] = [
                    e for (e, _), h in zip(case["expectations"], hits) if not h
                ]
        for cond, (label, handling) in {
            "a_legacy_index_legacy_query": ("legacy", legacy_query),
            "b_legacy_index_new_query": ("legacy", lambda q: q),
            "c_new_index_new_query": ("new", lambda q: q),
        }.items():
            passages = indexes[label]
            scored = ranked(emb, passages, handling(queries["long"]))
            row[f"long_{cond}"] = case["target"] in {
                passages[i][0] for _, i in scored[:TOP_K]
            }
        rows.append(row)
    return {"snapshot": name, "source_checks": checks, "corpus": len(corpus),
            "passages": {k: len(v) for k, v in indexes.items()}, "cases": rows}


def run_multilingual(repo: Path, idx: Index) -> dict:
    arts = [a for a in cov.load_artifacts(repo) if not a.is_code]
    files: dict[str, set[str]] = defaultdict(set)
    for a in arts:
        for line in a.text.splitlines():
            s = line.strip()
            if 15 <= len(s) <= 80 and len(CJK.findall(s)) * 2 >= len(s):
                files[s].add(a.relative_path)
    lines = sorted(s for s, paths in files.items() if len(paths) == 1)
    queries = random.Random(SEED).sample(lines, min(150, len(lines)))
    emb = idx.emb
    emb.ensure(queries, label="multilingual queries")
    indexes = {
        "legacy": idx.legacy(arts),
        "new_repo_path": idx.fitted(arts, cov.factory("code")),
        "new_upload_path": idx.fitted(arts, cov.factory(None)),
    }
    out: dict = {"queries": len(queries), "corpus_artifacts": len(arts)}
    for label, passages in indexes.items():
        hits = 0
        for q in queries:
            gold = next(iter(files[q]))
            scored = ranked(emb, passages, q)
            hits += any(passages[i][1] == gold for _, i in scored[:5])
        out[label] = {"passages": len(passages), "hit@5": hits}
    return out


def verdict(snapshots: list[dict], multi: dict) -> dict:
    rows = [r for s in snapshots for r in s["cases"]]
    total = sum(r["expected"] for r in rows)
    legacy = sum(r["legacy_k3_delivered"] for r in rows)
    new = sum(r["new_k3_delivered"] for r in rows)
    margin = math.ceil(0.05 * total)
    d2 = [r["id"] for r in rows
          if r["new_k3_delivered"] < r["legacy_k3_delivered"] / 2]
    disc = {k: sum(r[f"{k}_discovered"] for r in rows) for k in ("legacy", "new")}
    longs = {c: sum(r[f"long_{c}"] for r in rows) for c in (
        "a_legacy_index_legacy_query", "b_legacy_index_new_query",
        "c_new_index_new_query")}
    m_margin = math.ceil(0.05 * multi["queries"])
    base = longs["a_legacy_index_legacy_query"]
    return {
        "D1": {"expected": total, "legacy": legacy, "new": new, "margin": margin,
               "pass": new >= legacy - margin},
        "D2": {"cases_losing_over_half": d2, "pass": not d2},
        "D3": {**disc, "pass": disc["new"] >= disc["legacy"] - 1},
        "D4": {
            "legacy": multi["legacy"]["hit@5"],
            "new_repo_path": multi["new_repo_path"]["hit@5"],
            "new_upload_path": multi["new_upload_path"]["hit@5"],
            "margin": m_margin,
            "pass": all(multi[k]["hit@5"] >= multi["legacy"]["hit@5"] - m_margin
                        for k in ("new_repo_path", "new_upload_path")),
        },
        "D5": {**longs, "pass": (
            longs["b_legacy_index_new_query"] >= base - 1
            and longs["c_new_index_new_query"] >= base - 1)},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lightrag", type=Path, required=True)
    ap.add_argument("--foundry-e1", type=Path, required=True)
    ap.add_argument("--foundry-r4", type=Path, required=True)
    ap.add_argument("--ollama", required=True)
    ap.add_argument("--cache-dir", type=Path, required=True)
    ap.add_argument("--json", type=Path, required=True)
    args = ap.parse_args()

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    emb = cov.Embeddings(args.ollama, args.cache_dir / "emb-cache-delivery.jsonl")
    idx = Index(emb)
    snapshots = [
        run_snapshot("lightrag@4d0afc1", args.lightrag, e1_cases("lightrag"), idx),
        run_snapshot("foundry@109f12d8", args.foundry_e1, e1_cases("foundry"), idx),
        run_snapshot("foundry@3ba6a2f", args.foundry_r4, r4_cases(), idx),
    ]
    multi = run_multilingual(args.lightrag, idx)
    out = {
        "protocol": "DOCS/evaluations/2026-11-10-ci06-delivery-evaluation-protocol.md",
        "serving": cov.serving_identity(args.ollama),
        "snapshots": snapshots,
        "multilingual": multi,
        "verdict": verdict(snapshots, multi),
    }
    args.json.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out["verdict"], indent=1))


if __name__ == "__main__":
    main()
