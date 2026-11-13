"""Bounded local E1 ablations. No runtime edits and no prototype model calls."""

from __future__ import annotations

import argparse
import asyncio
import copy
import importlib
import json
import logging
import re
import os
import sys
import time
from dataclasses import asdict, replace
from typing import Any

import httpx

import code_evidence_experiment as e1


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def is_symbol(canonical: str) -> bool:
    path, separator, name = canonical.partition("#")
    return bool(
        separator
        and path.endswith((".py", ".ts", ".js", ".rs", ".java"))
        and not name.startswith("import:")
    )


def symbol_score(canonical: str, query: str) -> tuple[int, int]:
    if not is_symbol(canonical):
        return 0, 0
    symbol = canonical.split("#", 1)[1]
    exact = bool(re.search(r"(?<!\w)" + re.escape(symbol) + r"(?!\w)", query))
    return int(exact), len(words(query) & words(symbol))


def rerank(discovered: list[str], query: str) -> list[str]:
    return sorted(
        discovered, key=lambda cid: tuple(-v for v in symbol_score(cid, query))
    )


def rank_for_arm(ranking: Any, arm: str, query: str):
    if arm == "discovery":
        return replace(ranking, expanded_ranked=rerank(ranking.expanded_ranked, query))
    return ranking


def source_priority(chunk: dict) -> int:
    cid = e1.label(chunk)
    path = cid.split("#", 1)[0]
    if path.startswith("docs-archive/"):
        return 4
    if any(part in ("tests", "test", "examples") for part in path.split("/")):
        return 2
    if path.endswith((".py", ".ts", ".js", ".rs", ".java")):
        return 0 if is_symbol(cid) else 1
    return 3


def allocate(chunks: list[dict], query: str) -> list[dict]:
    ordered = sorted(
        chunks,
        key=lambda c: (
            source_priority(c),
            *(-v for v in symbol_score(e1.label(c), query)),
        ),
    )
    unique = []
    seen = set()
    for chunk in ordered:
        key = (e1.label(chunk).split("#", 1)[0], e1.normalized(chunk["text"]))
        if key not in seen:
            unique.append(chunk)
            seen.add(key)
    return unique


def window(chunks: list[dict], query: str) -> list[dict]:
    ordered = sorted(chunks, key=lambda c: c["metadata"]["chunk_index"])
    count = min(5, len(ordered))
    if not count:
        return []

    def score(start: int) -> tuple[int, int, int]:
        operations = [
            line
            for c in ordered[start : start + count]
            for line in c["text"].splitlines()
            if not line.strip().startswith(("#", "def ", "async def ", "class "))
            and re.search(
                r"\b(await|return|if|for|while|raise)\b|(?<![=!<>])=(?!=)", line
            )
        ]
        return len(words("\n".join(operations)) & words(query)), len(operations), -start

    start = max(range(len(ordered) - count + 1), key=score)
    return ordered[start : start + count]


def configure(host: str):
    sys.path.insert(0, str(e1.ROOT))
    sys.path.insert(0, str(e1.ROOT / "rag_orchestrator"))
    config: Any = importlib.import_module("src.core.config")
    package: Any = importlib.import_module("rag_orchestrator.src.core.config")
    settings = config.Settings(
        _env_file=None,
        OLLAMA_BASE_URL=f"{host}:11434",
        INGESTION_SERVICE_URL=f"{host}:8001",
        VECTOR_STORE_URL=f"{host}:8002",
        LLM_SERVICE_URL=f"{host}:8003",
    )
    config.get_settings = lambda: settings
    package.get_settings = lambda: settings
    return importlib.import_module("src.core.service")


def request_key(url: str, body: dict) -> str:
    return url + json.dumps(body, sort_keys=True)


def serialize_mapping(mapping: dict) -> dict:
    return {doc: [asdict(c) for c in rows] for doc, rows in mapping.items()}


def deserialize_mapping(service: Any, mapping: dict) -> dict:
    return {
        doc: [service.RetrievedChunk(**c) for c in rows]
        for doc, rows in mapping.items()
    }


def allocation_for_budget(chunks, budget, arm, query, observed):
    if budget <= 4096:
        observed["unmodified_adapter_pool"] = chunks
        if arm == "allocation":
            return allocate(chunks, query)
    return chunks


async def capture(
    service: Any,
    case: dict,
    baseline: dict,
    manifest: dict,
    arm: str,
    control: dict | None = None,
    passages: dict | None = None,
) -> dict:
    observed, _, restore = e1.install_observers(service)
    observed.update(
        {
            "case_id": case["id"],
            "arm": arm,
            "scope": "Local dry-run generation payload, not delivered to model",
        }
    )
    observed_post = httpx.AsyncClient.post
    original_hybrid = service.hybrid_retrieve
    original_rank = service._rank_expanded_canonical_ids
    observed_assemble = service.assemble_context
    cache = {
        request_key(r["url"], r["request"]): r["response"]
        for r in baseline["retrieval_requests"]
    }

    async def replay_post(client, url, **kwargs):
        body = kwargs.get("json", {})
        if str(url).endswith("/generate"):
            observed["generation_request"] = body
            matched = body == baseline["generation_request"]
            observed["matches_original_generation_payload"] = matched
            data = (
                baseline["generation_response"]
                if arm == "control" and matched
                else {"response": "GENERATION_NOT_RUN: evidence-only local prototype"}
            )
            observed["model_invoked"] = False
            return httpx.Response(200, json=data, request=httpx.Request("POST", url))
        key = request_key(str(url), body)
        if key in cache:
            observed.setdefault("cached_api_requests", []).append(
                {"url": str(url), "request": body}
            )
            return httpx.Response(
                200, json=cache[key], request=httpx.Request("POST", url)
            )
        return await observed_post(client, url, **kwargs)

    def rank(*args, **kwargs):
        result = original_rank(*args, **kwargs)
        observed["original_expanded_order"] = result.expanded_ranked
        result = rank_for_arm(result, arm, case["query"])
        observed["expanded_order"] = result.expanded_ranked
        return result

    async def hybrid(*args, **kwargs):
        if control is not None:
            raw = passages if passages is not None else control["retrieved_by_document"]
            mapping = deserialize_mapping(service, raw)
            plan = copy.deepcopy(control["hybrid_plan"])
            plan.pop("_evidence_trace_partial", None)
        else:
            mapping, plan = await original_hybrid(*args, **kwargs)
        observed["retrieved_by_document"] = serialize_mapping(mapping)
        observed["hybrid_plan"] = copy.deepcopy(plan)
        return mapping, plan

    def assemble(chunks, budget):
        chunks = allocation_for_budget(chunks, budget, arm, case["query"], observed)
        return observed_assemble(chunks, budget)

    setattr(httpx.AsyncClient, "post", replay_post)
    service.hybrid_retrieve = hybrid
    service._rank_expanded_canonical_ids = rank
    service.assemble_context = assemble
    service.embed_query = lambda *args, **kwargs: baseline["query_vector"]
    pin = manifest["pins"][case["repo"]]
    try:
        response = await service.run_rag(
            query=case["query"],
            repo_id=pin["repo_id"],
            top_k=20,
            max_chunks_per_doc=5,
            max_total_tokens=4096,
            model=manifest["model"],
            rerank=False,
            trace_canonical_ids=e1.case_ids(case),
            repository_overview_claim_selection_enabled=False,
            repository_overview_canonical_selection_enabled=False,
            repository_overview_structured_answers_enabled=False,
        )
        observed["response"] = response.model_dump(mode="json")
        observed["score"] = e1.score(case, manifest, observed)
        observed["score"]["answer_faithfulness"] = (
            "not evaluated; prototype generation skipped"
        )
        return observed
    except BaseException as error:
        observed["status"] = "incomplete-no-quality-score"
        observed["error"] = {"type": type(error).__name__, "message": str(error)}
        e1.write(e1.RESULTS / f"incomplete-{arm}-{case['id']}.json", observed)
        raise
    finally:
        service.hybrid_retrieve = original_hybrid
        service._rank_expanded_canonical_ids = original_rank
        restore()


async def fetch_windows(
    host: str, case: dict, control: dict, pin: dict
) -> tuple[dict, list]:
    mapping = copy.deepcopy(control["retrieved_by_document"])
    candidates = [
        (doc, e1.label(rows[0]))
        for doc, rows in mapping.items()
        if rows and is_symbol(e1.label(rows[0]))
    ]
    candidates.sort(
        key=lambda pair: tuple(-v for v in symbol_score(pair[1], case["query"]))
    )
    fetches = []
    async with httpx.AsyncClient(timeout=30) as client:
        for doc, canonical in candidates[:3]:
            body = {
                "document_id": doc,
                "k": 24,
                "repo_id": pin["repo_id"],
                "ingestion_id": pin["ingestion_id"],
            }
            start = time.monotonic()
            response = await client.post(
                f"{host}:8002/v1/vectors/search-by-doc", json=body
            )
            response.raise_for_status()
            rows = response.json()["results"]
            selected = window(rows, case["query"])
            fetches.append(
                {
                    "canonical_id": canonical,
                    "request": body,
                    "seconds": time.monotonic() - start,
                    "returned_records": len(rows),
                    "returned_text_bytes": sum(len(c["text"].encode()) for c in rows),
                    "returned_response_bytes": len(response.content),
                    "selected_ordinals": [
                        c["metadata"]["chunk_index"] for c in selected
                    ],
                    "response": response.json(),
                }
            )
            mapping[doc] = [
                {
                    "chunk_id": c["chunk_id"],
                    "document_id": doc,
                    "text": c["text"],
                    "score": c["score"],
                    "metadata": c["metadata"],
                    "canonical_id": canonical,
                    "chunk_index": c["metadata"]["chunk_index"],
                    "fetch_position": i,
                    "doc_type": c["metadata"]["source_metadata"].get("doc_type"),
                    "provenance": c["metadata"]["source_metadata"].get("provenance"),
                }
                for i, c in enumerate(selected)
            ]
    assert len(fetches) <= 3 and sum(f["returned_records"] for f in fetches) <= 72
    return mapping, fetches


async def main(host: str) -> None:
    manifest = e1.read(e1.DIRECTORY / "manifest.json")
    assert (
        e1.digest((e1.DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
        == (e1.DIRECTORY / "manifest.sha256").read_text().strip()
    )
    baselines = {
        c["id"]: e1.read(e1.RESULTS / f"baseline-{c['id']}.json")
        for c in manifest["cases"]
    }
    await e1.check_availability(host)
    service = configure(host)
    logging.disable(logging.CRITICAL)
    for case in manifest["cases"]:
        pin = manifest["pins"][case["repo"]]
        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{host}:8001/v1/repos/{pin['repo_id']}/generation"
            before = await client.get(url)
            before.raise_for_status()
            assert before.json()["ingestion_id"] == pin["ingestion_id"]
        base = baselines[case["id"]]
        control_path = e1.RESULTS / f"control-{case['id']}.json"
        if control_path.exists():
            control = e1.read(control_path)
        else:
            control = await capture(service, case, base, manifest, "control")
            e1.write(control_path, control)
        print(
            case["id"],
            "control matched",
            control["matches_original_generation_payload"],
            flush=True,
        )
        for arm in ("discovery", "passage", "allocation"):
            path = e1.RESULTS / f"{arm}-{case['id']}.json"
            if path.exists():
                continue
            if arm == "passage":
                mapping, fetches = await fetch_windows(host, case, control, pin)
                record = await capture(
                    service, case, base, manifest, arm, control, mapping
                )
                record["targeted_fetches"] = fetches
            else:
                record = await capture(
                    service,
                    case,
                    base,
                    manifest,
                    arm,
                    None if arm == "discovery" else control,
                )
            if arm == "allocation":
                assert (
                    record["unmodified_adapter_pool"]
                    == control["unmodified_adapter_pool"]
                )
            record["discovery_plan_scope"] = (
                "Control discovery trace retained for fixed-document arms; "
                "passage counts are in targeted_fetches"
            )
            e1.write(path, record)
            print(
                case["id"],
                arm,
                "survival",
                record["score"]["target_survived"],
                "operations",
                record["score"]["operation_coverage"]["satisfied"],
                "dependencies",
                record["score"]["dependency_coverage"]["satisfied"],
                flush=True,
            )
        async with httpx.AsyncClient(timeout=30) as client:
            after = await client.get(url)
            after.raise_for_status()
            assert after.json() == before.json()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("E1_HOST"))
    host = parser.parse_args().host
    if not host:
        parser.error("--host or E1_HOST is required (e.g. http://<host>)")
    asyncio.run(main(host))
