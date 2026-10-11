"""Replay saved R1/R2 requests through local ASGI using remote read-only services.

Run from rag_orchestrator/ so its service-local imports and settings match tests.
The observation wrapper calls the unmodified selection function and records
identities only. Its trace-off comparison is pure selection, not another query.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "R1_cli_tool_flow", "R2_provider_switch", "R1_cli_tool_flow_explicit",
    "R2_provider_switch_explicit", "R1_cli_tool_flow_explicit_normal_mode",
}
SETTING_KEYS = (
    "EMBEDDING_PROVIDER", "OLLAMA_EMBED_MODEL", "MAX_EXPANDED_DOCS",
    "EXPANDED_DOC_CHUNKS", "MAX_TOTAL_CHUNKS", "CONTEXT_WINDOW_TOKENS",
    "PROMPT_RESERVE_TOKENS", "OUTPUT_RESERVE_TOKENS", "MAX_CONCURRENT_DOC_FETCHES",
    "DOC_TYPE_TIE_BREAK_ENABLED", "DOC_TYPE_TIE_BREAK_SEED_POOL_SIZE",
    "DOC_TYPE_TIE_BREAK_EPSILON", "RERANK_ENABLED", "RERANK_TOP_K",
    "REPOSITORY_OVERVIEW_CANONICAL_SELECTION_ENABLED",
    "REPOSITORY_OVERVIEW_CLAIM_SELECTION_ENABLED",
    "REPOSITORY_OVERVIEW_STRUCTURED_ANSWERS_ENABLED",
    "REPOSITORY_OVERVIEW_TYPED_FACT_EXPERIMENT",
)


def read(url):
    with urlopen(url, timeout=30) as response:
        return json.load(response)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def describe(chunk):
    def value(name):
        return chunk.get(name) if isinstance(chunk, dict) else getattr(chunk, name)

    return {key: value(key) for key in (
        "canonical_id", "document_id", "chunk_id", "chunk_index", "fetch_position",
    )}


def parity(old, new):
    fields = (
        "seed_canonical_ids", "expanded_canonical_ids",
        "chunks_returned_by_document", "final_context_manifest",
        "tokens_before_budget", "tokens_after_budget", "context_budget",
    )
    return {key: old.get(key) == new.get(key) for key in fields}


async def run(args):
    os.environ.update({
        "INGESTION_SERVICE_URL": args.ingestion,
        "VECTOR_STORE_URL": args.vectors,
        "LLM_SERVICE_URL": args.llm,
        "OLLAMA_BASE_URL": args.ollama,
    })
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "rag_orchestrator"))
    import httpx
    from fastapi import FastAPI
    from src.api.v1 import routes
    from src.core import service

    logging.disable(logging.INFO)
    source = json.loads(args.input.read_text(encoding="utf-8"))
    generation_url = f"{args.ingestion}/v1/repos/{source['repo_id']}/generation"

    def generation():
        current = read(generation_url)
        assert current["generation_status"] == "ready", current
        assert current["ingestion_id"] == source["expected_generation"], current
        assert current["commit_sha"] == source["expected_source_sha"], current
        return current

    generation()
    models = read(f"{args.orchestrator}/v1/models")
    default = next(m for m in models["models"] if m.get("is_default"))
    assert default["model"] == "ollama/Qwen3:4b", default
    settings = service.get_settings()
    original = service.prepare_chunks_for_agent
    allocations = []

    def observe(*positional, **kwargs):
        result = original(*positional, **kwargs)
        plain_kwargs = {**kwargs, "selection_trace": None}
        assert result == original(*positional, **plain_kwargs), "selection changed"
        context = positional[0]
        order = kwargs.get("document_order") or sorted(context.chunks_by_document)
        allocations.append({
            "max_chunks_per_doc": kwargs.get("max_chunks_per_doc", 5),
            "max_total_chunks": kwargs.get("max_total_chunks", 50),
            "trace_off_selection_identical": True,
            "documents": [
                {"document_position": i, "document_id": doc,
                 "chunks": [describe(c) for c in context.chunks_by_document[doc]]}
                for i, doc in enumerate(order)
                if doc in context.chunks_by_document
            ],
            "accepted_chunks": [describe(c) for c in result],
        })
        return result

    service.prepare_chunks_for_agent = observe
    app = FastAPI()
    app.include_router(routes.router, prefix="/v1")
    result = {
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "transport": "local ASGI /v1/rag; remote generation/graph/vector/LLM/embedding",
        "local_code_commit": git("rev-parse", "HEAD"),
        "python": platform.python_version(), "platform": platform.platform(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "historical_artifact_sha256": hashlib.sha256(
            args.input.read_bytes(),
        ).hexdigest(),
        "historical_runtime": source["runtime_version"],
        "current_remote_runtime": read(f"{args.orchestrator}/version"),
        "runtime_files_different_from_deployed": git(
            "diff", "--name-only", source["runtime_version"]["git_sha"], "HEAD",
            "--", "rag_orchestrator/src", "shared",
        ).splitlines(),
        "expected_generation": source["expected_generation"],
        "expected_source_sha": source["expected_source_sha"],
        "repo_id": source["repo_id"],
        "effective_local_settings": {k: getattr(settings, k) for k in SETTING_KEYS},
        "model_default": default,
        "ollama_model_digests": [
            {"name": m["name"], "digest": m["digest"]}
            for m in read(f"{args.ollama}/api/tags")["models"]
            if m["name"] in {"Qwen3:4b", settings.OLLAMA_EMBED_MODEL}
        ],
        "cases": [],
    }

    def save():
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://local-diagnostic",
        ) as client:
            for old in source["cases"] + source["follow_up_variants"]:
                if old["name"] not in CASES:
                    continue
                allocations.clear()
                before = generation()
                print(f"START {old['name']}", flush=True)
                start = time.monotonic()
                response = await client.post("/v1/rag", json=old["request"])
                row = {
                    "name": old["name"], "request": old["request"],
                    "generation_before": before, "generation_after": generation(),
                    "elapsed_seconds": round(time.monotonic() - start, 2),
                    "http_status": response.status_code, "response": response.json(),
                    "adapter_allocations": list(allocations),
                    "historical_trace_id": old["response"]["trace_id"],
                }
                result["cases"].append(row)
                save()
                response.raise_for_status()
                body = row["response"]
                plan = body["retrieval_plan"]
                assert plan["generation_id"] == source["expected_generation"]
                assert body["repo_id"] == source["repo_id"]
                assert body["model_used"] == "ollama/Qwen3:4b", body["model_used"]
                row["historical_retrieval_parity"] = parity(
                    old["response"]["retrieval_plan"], plan,
                )
                save()
                print(json.dumps({
                    "case": old["name"], "elapsed_seconds": row["elapsed_seconds"],
                    "parity": row["historical_retrieval_parity"],
                    "agent_run_exclusions": [r for r in plan["chunk_selection_trace"]
                        if r["canonical_id"] == "py_mono/agent/agent.py#Agent.run"],
                }), flush=True)
    finally:
        service.prepare_chunks_for_agent = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ingestion", "vectors", "llm", "ollama", "orchestrator"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
