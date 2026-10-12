"""Observe the unchanged candidate's R1 selection and LLM HTTP payload.

Observers copy diagnostic data and return the original results unchanged.
Full-document reads are an out-of-band inventory, never retrieval inputs.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from importlib import import_module
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from issue240_overview_eval import fetch, generation


ROOT = Path(__file__).resolve().parents[1]


def capture_chunks(chunks) -> list[dict]:
    """Copy chunk data without changing the objects the runtime uses."""
    return [asdict(c) if not isinstance(c, dict) else json.loads(json.dumps(c))
            for c in chunks]


def observe_sync(function, snapshot):
    def observed(*args, **kwargs):
        result = function(*args, **kwargs)
        snapshot(args, kwargs, result)
        return result
    return observed


async def run(args) -> None:  # noqa: C901 - observes the existing stage boundaries
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "rag_orchestrator"))
    config = import_module("src.core.config")
    Settings, get_settings = config.Settings, config.get_settings

    Settings.model_config["env_file"] = None
    import os
    previous_runtime = json.loads(args.runtime.read_text(encoding="utf-8"))
    for key, value in previous_runtime["local_settings"].items():
        if isinstance(value, (str, int, float, bool)):
            os.environ[key] = str(value)
    get_settings.cache_clear()
    service: Any = import_module("src.core.service")

    # Service imports configure logging; keep the observer run quiet.
    logging.disable(logging.CRITICAL)
    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    pin = next(c for c in comparison["contract"] if c["dataset"] == "agent")
    settings = get_settings()
    result = {
        "status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "bounded completeness diagnosis; no retrieval changes",
        "pin": pin, "settings": settings.model_dump(mode="json"),
        "candidate_source_sha256": previous_runtime["changed_source_sha256"],
        "versions": {name: fetch(f"{url}/version") for name, url in (
            ("ingestion", settings.INGESTION_SERVICE_URL),
            ("vector", settings.VECTOR_STORE_URL), ("llm", settings.LLM_SERVICE_URL),
        )},
        "cases": [], "inventory": {},
    }
    for path, digest in result["candidate_source_sha256"].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Candidate changed before diagnosis: {path}")

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    active = {}

    def record(stage, chunks, **details):
        active.setdefault("stages", []).append({
            "stage": stage, "chunks": capture_chunks(chunks), **details,
        })

    original_hybrid = service.hybrid_retrieve

    async def hybrid(*a, **kw):
        retrieved, plan = await original_hybrid(*a, **kw)
        active["retrieved_by_document"] = {
            doc: capture_chunks(chunks) for doc, chunks in retrieved.items()
        }
        return retrieved, plan

    service.hybrid_retrieve = hybrid
    service.execute_retrieval_plan = observe_sync(
        service.execute_retrieval_plan,
        lambda a, kw, out: record(
            "plan_slice", [c for cs in out.chunks_by_document.values() for c in cs],
            top_k_per_document=kw["top_k_per_document"],
        ),
    )
    service.prepare_chunks_for_agent = observe_sync(
        service.prepare_chunks_for_agent,
        lambda a, kw, out: record("adapter_selection", out, **{
            key: kw.get(key) for key in
            ("document_order", "max_chunks_per_doc", "max_total_chunks")
        }),
    )
    original_policy = service._apply_overview_selection

    async def policy(*a, **kw):
        record("policy_input", a[0])
        out = await original_policy(*a, **kw)
        record("policy_output", out[0], obligation=out[2], selection_trace=out[3])
        return out

    service._apply_overview_selection = policy
    service.prioritize_exact_sources = observe_sync(
        service.prioritize_exact_sources,
        lambda a, kw, out: record("exact_source_order", out[0], trace=out[1]),
    )
    service.assemble_context = observe_sync(
        service.assemble_context,
        lambda a, kw, out: record("assembly", out.chunks,
                                 input_chunks=capture_chunks(a[0]),
                                 budget=a[1], consumed=out.token_count),
    )
    original_send = httpx.AsyncClient.send

    async def send(self, request, *a, **kw):
        response = await original_send(self, request, *a, **kw)
        if request.url.path in (
            "/v1/vectors/search", "/v1/vectors/search-by-doc", "/generate",
        ):
            active.setdefault("wire", []).append({
                "url": str(request.url), "request": json.loads(request.content),
                "status": response.status_code, "response": response.json(),
            })
        return response

    httpx.AsyncClient.send = send
    save()
    try:
        for arm in ("candidate", "overview_off"):
            row = next(r for r in comparison["results"]
                       if r["case"] == "R1" and r["arm"] == arm)
            active = {"arm": arm, "request": row["request"]}
            result["cases"].append(active)
            active["generation_before"] = generation(
                settings.INGESTION_SERVICE_URL, pin["repo_id"],
                pin["pin"]["ingestion_id"], pin["pin"]["commit_sha"],
            )
            print(f"Starting observed R1 {arm}", flush=True)
            active["response"] = (await service.run_rag(**row["request"])).model_dump()
            active["generation_after"] = generation(
                settings.INGESTION_SERVICE_URL, pin["repo_id"],
                pin["pin"]["ingestion_id"], pin["pin"]["commit_sha"],
            )
            save()
            print(f"Completed observed R1 {arm}", flush=True)
        # Enumerate persisted chunks only after the unmodified query runs.
        for entry in result["cases"][0]["response"]["retrieval_plan"]["evidence_trace"]:
            request = {
                "document_id": entry["document_id"], "k": 100,
                "repo_id": pin["repo_id"], "ingestion_id": pin["pin"]["ingestion_id"],
            }
            result["inventory"][entry["canonical_id"]] = {
                "request": request,
                "response": fetch(
                    f"{settings.VECTOR_STORE_URL}/v1/vectors/search-by-doc", request
                ),
            }
        result["generation_after_inventory"] = generation(
            settings.INGESTION_SERVICE_URL, pin["repo_id"],
            pin["pin"]["ingestion_id"], pin["pin"]["commit_sha"],
        )
        # Observe the within-artifact ranking beyond the runtime's k=3 cut.
        # This read is never fed back into retrieval or the LLM payload.
        run_document = next(
            e["document_id"] for e in result["cases"][0]["response"]
            ["retrieval_plan"]["evidence_trace"]
            if e["canonical_id"].endswith("agent.py#Agent.run")
        )
        wire_fetch = next(
            w for w in result["cases"][0]["wire"]
            if w["url"].endswith("/search-by-doc")
            and w["request"]["document_id"] == run_document
        )
        rank_request = {**wire_fetch["request"], "k": 100}
        ranked = fetch(wire_fetch["url"], rank_request)
        if ([r["chunk_id"] for r in ranked["results"][:3]] !=
                [r["chunk_id"] for r in wire_fetch["response"]["results"]]):
            raise RuntimeError("Rank inventory does not reproduce observed fetch")
        result["rank_inventory"] = {
            "purpose": (
                "out-of-band rank inventory; never supplied to RAG or generation"
            ),
            "request": rank_request, "response": ranked,
            "top_three_match_observed_fetch": True,
        }
        result["generation_after_rank_inventory"] = generation(
            settings.INGESTION_SERVICE_URL, pin["repo_id"],
            pin["pin"]["ingestion_id"], pin["pin"]["commit_sha"],
        )
        result["versions_after"] = {name: fetch(f"{url}/version") for name, url in (
            ("ingestion", settings.INGESTION_SERVICE_URL),
            ("vector", settings.VECTOR_STORE_URL), ("llm", settings.LLM_SERVICE_URL),
        )}
        if result["versions_after"] != result["versions"]:
            raise RuntimeError("Upstream runtime changed during diagnosis")
        result["status"] = "complete"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        result["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    if options.output.exists():
        raise SystemExit("Refusing to overwrite a diagnostic run")
    asyncio.run(run(options))
