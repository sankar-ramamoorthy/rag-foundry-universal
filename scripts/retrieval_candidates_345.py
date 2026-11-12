"""Issue #345/#342: capture the retrieval candidates for the Step 0 question.

Runs the unchanged local orchestrator (`run_rag`) against the deployed
read-only services, with llm_service replaced by a local stub so that no
generation happens. The only model call is the query embedding. Nothing is
written to any service; the repository generation is checked to be
unchanged before and after.

Records, without interpretation:

- the seed vector search (request filter, k, every result with score),
- the pre-budget candidate pool (`assemble_context(..., 2**63)` input) and
  the final context, each chunk with its label, document, bytes and rank,
- `retrieval_plan` including the evidence trace for the reviewed witnesses,
- a deep vector ranking (one read-only search with a large k) giving each
  witness's similarity rank,
- fidelity: whether the reproduced final context is byte-identical to the
  Step 0 capture's context (sha256).

    python scripts/retrieval_candidates_345.py CAPTURE.json --host http://HOST \
        --out RAW/2026-11-12-345-retrieval-candidates.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import logging
import os
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import inference_pilot_345 as pilot  # noqa: E402

SCHEMA = "retrieval_candidates_345.v1"
DEEP_K = 2000

# Reviewed implementation witnesses for the Step 0 question (canonical ids as
# ingested; ADR-031 `path#Symbol`).
WITNESSES = [f"{path}#{symbol}" for path, symbol, _ in pilot.IMPLEMENTATION_EXCERPTS]
WITNESSES.insert(
    WITNESSES.index("shared/embedders/query.py#embed_query"),
    "shared/embedders/factory.py#get_embedder",
)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _LLMStub(BaseHTTPRequestHandler):
    """Stands in for llm_service /generate: records the payload, answers a
    fixed string. No model is called."""

    payloads: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).payloads.append({"path": self.path, "json": body})
        data = json.dumps(
            {"response": "(stub: no generation)", "model": "stub"}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def nodes_of(lookup: dict) -> dict:
    return {
        n["canonical_id"]: n
        for n in lookup.get("nodes", [])
        if n["canonical_id"] in WITNESSES
    }


def similarity_position(score: float | None, deep_scores: list[float]) -> dict:
    """Where a score would sit in the deep ranking (same filter)."""
    if score is None:
        return {"rank": None, "beyond_deep_k": None}
    better = sum(1 for s in deep_scores if s > score)
    beyond = bool(deep_scores) and score < deep_scores[-1]
    return {"rank": None if beyond else better + 1, "beyond_deep_k": beyond}


def chunk_row(rank: int, chunk: dict, label_of) -> dict:
    text = str(chunk.get("text", ""))
    meta = chunk.get("metadata") or {}
    nested = meta.get("source_metadata") if isinstance(meta, dict) else {}
    nested = nested if isinstance(nested, dict) else {}
    return {
        "rank": rank,
        "label": str(label_of(chunk)),
        "document_id": chunk.get("document_id"),
        "chunk_id": chunk.get("chunk_id"),
        "doc_type": nested.get("doc_type") or (meta or {}).get("doc_type"),
        "source_type": nested.get("source_type") or (meta or {}).get("source_type"),
        "score": chunk.get("score"),
        "bytes": len(text.encode("utf-8")),
        "text_sha256": sha256(text),
    }


async def capture(args: argparse.Namespace) -> dict:
    import httpx

    record = json.loads(args.capture.read_text(encoding="utf-8"))
    context, query = pilot.split_user_message(
        record["application_input"]["messages"][1]["content"]
    )
    repo_id = record["repo_id"]

    server = HTTPServer(("127.0.0.1", 0), _LLMStub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    stub_url = f"http://127.0.0.1:{server.server_port}"

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "rag_orchestrator"))
    config: Any = importlib.import_module("src.core.config")
    from rag_orchestrator.src.core import config as package_config

    settings = config.Settings(
        _env_file=None,
        OLLAMA_BASE_URL=f"{args.host}:11434",
        INGESTION_SERVICE_URL=f"{args.host}:8001",
        VECTOR_STORE_URL=f"{args.host}:8002",
        LLM_SERVICE_URL=stub_url,
    )
    config.get_settings = lambda: settings
    package_config.get_settings = lambda: settings
    service: Any = importlib.import_module("src.core.service")
    label_of = importlib.import_module("src.retrieval.agent_adapter")._source_label

    observed: dict = {"vector_searches": []}
    original_post = httpx.AsyncClient.post
    original_assemble = service.assemble_context
    original_embed = service.embed_query

    async def observe_post(client, url, **kwargs):
        response = await original_post(client, url, **kwargs)
        if str(url).endswith("/v1/vectors/search"):
            req = dict(kwargs.get("json") or {})
            req.pop("query_vector", None)
            observed["vector_searches"].append(
                {"request": req, "results": response.json().get("results", [])}
            )
        return response

    def observe_assemble(chunks, budget):
        result = original_assemble(chunks, budget)
        if budget > 10**9:
            observed["pre_budget_chunks"] = list(chunks)
        else:
            observed["final_budget"] = budget
            observed["final_chunks"] = list(result.chunks)
        return result

    def observe_embed(*a, **kw):
        observed["query_vector"] = original_embed(*a, **kw)
        return observed["query_vector"]

    httpx.AsyncClient.post = observe_post  # type: ignore[method-assign]
    service.assemble_context = observe_assemble
    service.embed_query = observe_embed
    logging.disable(logging.CRITICAL)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            gen_url = f"{args.host}:8001/v1/repos/{repo_id}/generation"
            before = (await client.get(gen_url)).json()
            versions = {
                port: (await client.get(f"{args.host}:{port}/version")).json()
                for port in ("8001", "8002", "8003", "8004")
            }
        result = await service.run_rag(
            query=query,
            repo_id=repo_id,
            trace_canonical_ids=set(WITNESSES),
        )
        async with httpx.AsyncClient(timeout=60) as client:
            after = (await client.get(gen_url)).json()
            lookup = (
                await client.post(
                    f"{args.host}:8001/v1/graph/repos/{repo_id}/nodes/lookup",
                    json={"canonical_ids": WITNESSES},
                )
            ).json()
            seed_filter = observed["vector_searches"][0]["request"]["metadata_filter"]
            deep = (
                await client.post(
                    f"{args.host}:8002/v1/vectors/search",
                    json={
                        "query_vector": observed["query_vector"],
                        "k": DEEP_K,
                        "metadata_filter": seed_filter,
                    },
                )
            ).json()["results"]
            witness_chunks = {}
            for w, doc in (
                (w, n["document_id"]) for w, n in nodes_of(lookup).items()
            ):
                witness_chunks[w] = (
                    await client.post(
                        f"{args.host}:8002/v1/vectors/search-by-doc",
                        json={
                            "document_id": doc,
                            "k": 50,
                            "query_vector": observed["query_vector"],
                            "ingestion_id": seed_filter["ingestion_id"],
                            "repo_id": repo_id,
                        },
                    )
                ).json()["results"]
    finally:
        httpx.AsyncClient.post = original_post  # type: ignore[method-assign]
        service.assemble_context = original_assemble
        service.embed_query = original_embed
        server.shutdown()
        server.server_close()

    generated = [p for p in _LLMStub.payloads if p["path"].startswith("/generate")]
    final_context = generated[0]["json"]["context"] if generated else None
    nodes = nodes_of(lookup)
    deep_scores = [float(r.get("score") or 0) for r in deep]
    seed_scores = [
        float(r.get("score") or 0) for r in observed["vector_searches"][0]["results"]
    ]
    witness_doc_ids = {
        w: nodes[w]["document_id"] for w in WITNESSES if w in nodes
    }
    deep_rank: dict[str, int] = {}
    for rank, r in enumerate(deep, 1):
        doc = r.get("document_id")
        for w, d in witness_doc_ids.items():
            if d == doc and w not in deep_rank:
                deep_rank[w] = rank
    pool = observed.get("pre_budget_chunks", [])
    final = observed.get("final_chunks", [])
    final_ids = {c.get("chunk_id") for c in final}
    plan = result.retrieval_plan
    return {
        "schema": SCHEMA,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "scope": (
            "Unchanged local orchestrator (git HEAD) against deployed read-only "
            "services; llm_service replaced by a local stub (no generation)."
        ),
        "git_head": os.popen("git rev-parse HEAD").read().strip(),
        "service_versions": versions,
        "local_settings": settings.model_dump(mode="json"),
        "repo_id": repo_id,
        "query_sha256": sha256(query),
        "generation_before": before,
        "generation_after": after,
        "generation_unchanged": before == after,
        "step0_generation_id": record.get("generation_id"),
        "fidelity": {
            "step0_context_sha256": record["application_input"]["context_sha256"],
            "reproduced_context_sha256": (
                sha256(final_context) if final_context else None
            ),
            "identical": bool(final_context)
            and sha256(final_context) == record["application_input"]["context_sha256"],
            "step0_context_bytes": len(context.encode("utf-8")),
            "reproduced_context_bytes": len(final_context.encode("utf-8"))
            if final_context
            else None,
        },
        "seed_searches": [
            {
                "request": s["request"],
                "results": [
                    chunk_row(i, r, label_of) for i, r in enumerate(s["results"], 1)
                ],
            }
            for s in observed["vector_searches"]
        ],
        "pre_budget_pool": [
            {**chunk_row(i, c, label_of), "in_final": c.get("chunk_id") in final_ids}
            for i, c in enumerate(pool, 1)
        ],
        "final_budget_bytes": observed.get("final_budget"),
        "final_context_chunks": [
            chunk_row(i, c, label_of) for i, c in enumerate(final, 1)
        ],
        "witnesses": [
            {
                "canonical_id": w,
                "in_repo_generation": w in nodes,
                "document_id": witness_doc_ids.get(w),
                "deep_vector_rank": deep_rank.get(w),
                "deep_k": DEEP_K,
                "vector_chunks": [
                    {
                        "chunk_index": (r.get("metadata") or {}).get("chunk_index"),
                        "score": r.get("score"),
                        "bytes": len(str(r.get("text", "")).encode("utf-8")),
                        "source_type": ((r.get("metadata") or {}).get(
                            "source_metadata") or {}).get("source_type"),
                        "doc_type": ((r.get("metadata") or {}).get(
                            "source_metadata") or {}).get("doc_type"),
                    }
                    for r in witness_chunks.get(w, [])
                ],
                "best_score": max(
                    (float(r.get("score") or 0) for r in witness_chunks.get(w, [])),
                    default=None,
                ),
                "best_score_position": similarity_position(
                    max(
                        (float(r.get("score") or 0) for r in witness_chunks.get(w, [])),
                        default=None,
                    ),
                    deep_scores,
                ),
                "in_pre_budget_pool": any(
                    str(label_of(c)) == w for c in pool
                ),
                "in_final_context": any(str(label_of(c)) == w for c in final),
            }
            for w in WITNESSES
        ],
        "seed_score_range": [
            min(seed_scores, default=None), max(seed_scores, default=None)
        ],
        "deep_score_at_k": deep_scores[-1] if deep_scores else None,
        "deep_doc_type_counts": _counts(deep, "doc_type"),
        "query_vector": observed["query_vector"],
        "evidence_trace": plan.get("evidence_trace"),
        "retrieval_plan": plan,
        "pool_texts": {
            c.get("chunk_id"): str(c.get("text", "")) for c in pool
        },
    }


def _counts(rows: list, key: str) -> dict:
    out: dict = {}
    for r in rows:
        v = ((r.get("metadata") or {}).get("source_metadata") or {}).get(key)
        out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("capture", type=Path)
    parser.add_argument("--host", required=True, help="scheme://host of services")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    data = asyncio.run(capture(args))
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({k: data[k] for k in ("fidelity", "generation_unchanged")}))
    print(json.dumps({k: data[k] for k in (
        "seed_score_range", "deep_score_at_k", "deep_doc_type_counts")}))
    for w in data["witnesses"]:
        print(json.dumps({k: w[k] for k in (
            "canonical_id", "best_score", "best_score_position", "deep_vector_rank",
            "in_pre_budget_pool")} | {"chunks": len(w["vector_chunks"]),
            "types": sorted({(c["source_type"], c["doc_type"])
                             for c in w["vector_chunks"]}, key=str)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
