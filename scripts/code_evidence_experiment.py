"""Local, read-only code-evidence experiment; never changes runtime policy.

Run with the repository virtual environment. Freeze reads PostgreSQL through
the existing personal db_inspect.py connection. Baseline runs unchanged local
orchestrator code against service HTTP endpoints and records the generation
payload. Commands refuse to overwrite a frozen suite or completed capture.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import logging
import os
import runpy
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "DOCS/evaluations/code-evidence-e1"
RESULTS = ROOT / "DOCS/test_results/code-evidence-e1"
# Bulky raw captures: git-ignored, tracked via DOCS/test_results/raw-index.json.
RAW = ROOT / "DOCS/test_results/_raw/code-evidence-e1"
F = "rag_orchestrator/src/"
L = "lightrag/operate.py#"
REPOS = {
    "lightrag": "4f76a36f-caf8-5532-9ee2-977ec412ed6c",
    "foundry": "f7641840-ba13-5f9d-9ae6-87e1f924709d",
}


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalized(text: str) -> str:
    return "".join(text.split())


def obligation(name: str, canonical: str, *expressions: str) -> dict:
    return {"name": name, "canonical_id": canonical, "expressions": list(expressions)}


def case_ids(case: dict) -> set[str]:
    return {case["target"]} | {
        o["canonical_id"] for o in case["operations"] + case["dependencies"]
    }


def definitions() -> list[dict]:
    trunc = L + "_apply_token_truncation"
    build = L + "_build_context_str"
    loop = L + "_build_query_context"
    adapter = F + "retrieval/agent_adapter.py#assemble_context"
    count = F + "retrieval/agent_adapter.py#conservative_token_count"
    cache = F + "retrieval/codebase_utils.py#get_cached_graph_with_generation"
    main = F + "core/service.py#run_rag"
    operations = [
        obligation(
            "Stage 2 dispatch",
            loop,
            "truncation_result = await _apply_token_truncation(",
            "search_result, query_param, text_chunks_db.global_config",
        ),
        obligation(
            "Entity limit operation",
            trunc,
            "entities_context = await atruncate_list_by_token_size(",
            "max_token_size=max_entity_tokens",
        ),
        obligation(
            "Relationship limit operation",
            trunc,
            "relations_context = await atruncate_list_by_token_size(",
            "max_token_size=max_relation_tokens",
        ),
        obligation(
            "Combined remainder and consumer",
            build,
            "available_chunk_tokens = max_total_tokens - (",
            "sys_prompt_tokens + kg_context_tokens + query_tokens + buffer_tokens",
            "chunk_token_limit=available_chunk_tokens",
        ),
    ]
    dependencies = [
        obligation(
            "Stage 3 uses truncated graph results",
            loop,
            'filtered_entities=truncation_result["filtered_entities"]',
            'filtered_relations=truncation_result["filtered_relations"]',
        ),
        obligation(
            "Entity branch and input",
            trunc,
            "if entities_context:",
            "entities_context_for_truncation.append(entity_copy)",
        ),
        obligation(
            "Relationship branch and input",
            trunc,
            "if relations_context:",
            "relations_context_for_truncation.append(relation_copy)",
        ),
        obligation(
            "Graph cost is calculated before remainder",
            build,
            "kg_context_tokens = await acount_tokens(tokenizer, pre_kg_context)",
            'text_chunks_str=""',
        ),
    ]
    return [
        {
            "id": "L1",
            "repo": "lightrag",
            "shape": "long function / cross-file budget evidence",
            "target": loop,
            "query": (
                "Find the implementation of `_build_query_context` in `lightr"
                "ag/operate.py`. Explain how it selects entities, relationshi"
                "ps, and text chunks, and how it applies `max_total_tokens`."
            ),
            "operations": operations,
            "dependencies": dependencies,
        },
        {
            "id": "L2",
            "repo": "lightrag",
            "shape": "natural-language implementation discovery",
            "target": loop,
            "query": (
                "Which function constructs the context for LightRAG graph que"
                "ries in local, global, hybrid, and mix modes? Explain how th"
                "e entity, relationship, and total token limits interact."
            ),
            "operations": operations,
            "dependencies": dependencies,
        },
        {
            "id": "L3",
            "repo": "lightrag",
            "shape": "long function / independent conditional branches",
            "target": trunc,
            "query": (
                "In `lightrag/operate.py`, how does `_apply_token_truncation`"
                " limit entities and relationships, and what fields are exclu"
                "ded from their token calculations? Does this function enforc"
                "e max_total_tokens?"
            ),
            "operations": operations[1:3]
            + [
                obligation(
                    "Entity fields removed",
                    trunc,
                    'entity_copy.pop("file_path", None)',
                    'entity_copy.pop("created_at", None)',
                ),
                obligation(
                    "Relationship fields removed",
                    trunc,
                    'relation_copy.pop("file_path", None)',
                    'relation_copy.pop("created_at", None)',
                ),
            ],
            "dependencies": dependencies[1:3]
            + [
                obligation(
                    "Independent limits loaded",
                    trunc,
                    '"max_entity_tokens"',
                    '"max_relation_tokens"',
                )
            ],
        },
        {
            "id": "F1",
            "repo": "foundry",
            "shape": "conditional skip / cross-file byte counting",
            "target": adapter,
            "query": (
                "In `rag_orchestrator/src/retrieval/agent_adapter.py`, how do"
                "es `assemble_context` handle a passage that exceeds the rema"
                "ining budget? Explain byte accounting, labels, separators, a"
                "nd whether later passages can still be included."
            ),
            "operations": [
                obligation(
                    "Render before accounting", adapter, "part = _render_chunk(chunk)"
                ),
                obligation(
                    "Separator-inclusive cost",
                    adapter,
                    "cost = conservative_token_count(part) + (2 if parts else 0)",
                ),
                obligation(
                    "Skip oversize passage",
                    adapter,
                    "if used + cost > max_total_tokens:",
                    "continue",
                ),
                obligation("UTF-8 counting", count, 'return len(text.encode("utf-8"))'),
            ],
            "dependencies": [
                obligation(
                    "Counter initialized", adapter, "used = 0", "parts: List[str] = []"
                ),
                obligation(
                    "Loop survives skipped item",
                    adapter,
                    "for chunk in agent_chunks:",
                    "parts.append(part)",
                    "used += cost",
                ),
                obligation(
                    "Only selected items returned",
                    adapter,
                    'return AssembledContext("\\n\\n".join(parts), selected, used)',
                ),
            ],
        },
        {
            "id": "F2",
            "repo": "foundry",
            "shape": "generation state / lock / LRU branches",
            "target": cache,
            "query": (
                "In `rag_orchestrator/src/retrieval/codebase_utils.py`, expla"
                "in how `get_cached_graph_with_generation` handles no ready g"
                "eneration, a warm matching cache entry, force_reload, and a "
                "changed generation. How is the cache kept bounded?"
            ),
            "operations": [
                obligation(
                    "Resolve generation each call",
                    cache,
                    "generation_id, status = get_repo_generation(repo_id)",
                ),
                obligation(
                    "Empty-generation return", cache, 'return "", CodebaseGraph()'
                ),
                obligation(
                    "Matching cached return", cache, "return generation_id, cached[1]"
                ),
                obligation(
                    "Reload and store",
                    cache,
                    "graph = load_graph_for_repo(repo_id)",
                    "_repo_graphs[repo_id] = (generation_id, graph)",
                ),
                obligation(
                    "LRU eviction",
                    cache,
                    "while len(_repo_graphs) > _CACHE_MAX_REPOS:",
                    "_repo_graphs.popitem(last=False)",
                ),
            ],
            "dependencies": [
                obligation(
                    "No generation condition", cache, "if generation_id is None:"
                ),
                obligation(
                    "Warm-hit condition",
                    cache,
                    (
                        "if not force_reload and cached is not None and cached[0] == "
                        "generation_id:"
                    ),
                ),
                obligation(
                    "Locked lookup and LRU refresh",
                    cache,
                    "with _repo_graphs_lock:",
                    "cached = _repo_graphs.get(repo_id)",
                    "_repo_graphs.move_to_end(repo_id)",
                ),
            ],
        },
        {
            "id": "F3",
            "repo": "foundry",
            "shape": "long async method / helper handoff / state dependencies",
            "target": main,
            "query": (
                "In `rag_orchestrator/src/core/service.py`, trace how `run_ra"
                "g` turns fetched passages into the actual LLM context. Expla"
                "in per-document/global chunk limits, the final byte allowanc"
                "e, and how the final manifest relates to the generation payl"
                "oad."
            ),
            "operations": [
                obligation(
                    "Adapter caps",
                    main,
                    "max_chunks_per_doc=max_chunks_per_doc",
                    "max_total_chunks=settings.MAX_TOTAL_CHUNKS",
                ),
                obligation(
                    "Budget min",
                    main,
                    "context_budget = min(",
                    "settings.CONTEXT_WINDOW_TOKENS",
                    "- conservative_token_count(query)",
                ),
                obligation(
                    "Assemble selected passages",
                    main,
                    "assembled = assemble_context(agent_chunks, context_budget)",
                ),
                obligation(
                    "Manifest uses assembled selection",
                    main,
                    "chunks_in_final_context = assembled.chunks",
                    "build_final_context_manifest(",
                    "chunks_in_final_context,",
                ),
                obligation(
                    "Generation receives context",
                    main,
                    'llm_payload = {"context": llm_context, "query": query}',
                    "json=llm_payload",
                ),
            ],
            "dependencies": [
                obligation(
                    "Reserve deductions",
                    main,
                    "- settings.PROMPT_RESERVE_TOKENS",
                    "- settings.OUTPUT_RESERVE_TOKENS",
                ),
                obligation(
                    "Context taken from assembled result",
                    main,
                    "context_str, token_count = assembled.text, assembled.token_count",
                    "llm_context = context_str",
                ),
                obligation(
                    "Overview alternative is conditional",
                    main,
                    'if claim_type == "repository_overview":',
                    (
                        'llm_context = policy_text + "\\nRETRIEVED EVIDENCE\\n" + conte'
                        "xt_str"
                    ),
                ),
            ],
        },
    ]


def freeze() -> None:
    import psycopg
    from psycopg.rows import dict_row

    path = DIRECTORY / "manifest.json"
    if path.exists():
        raise RuntimeError("Frozen manifest already exists; do not silently rewrite it")
    connection = runpy.run_path(str(ROOT / "scripts/db_inspect.py"))["CONN_DEFAULTS"]
    manifest = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "dataset_role": "development-regression; no held-out claim",
        "context_cap_bytes": 4096,
        "model": "ollama/Qwen3:4b",
        "top_k": 20,
        "max_chunks_per_doc": 5,
        "rerank": False,
        "cases": definitions(),
        "sources": {},
        "pins": {},
    }
    with psycopg.Connection[dict[str, Any]].connect(
        **connection,
        connect_timeout=10,
        options="-c default_transaction_read_only=on -c statement_timeout=30000",
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            for repo, repo_id in REPOS.items():
                cur.execute(
                    (
                        "SELECT ingestion_id, commit_sha, status FROM ingestion_servi"
                        "ce.ingestion_requests WHERE repo_id=%s AND status='completed"
                        "' ORDER BY finished_at DESC LIMIT 1"
                    ),
                    (repo_id,),
                )
                pin = cur.fetchone()
                assert pin is not None
                manifest["pins"][repo] = {**pin, "repo_id": repo_id}
            for case in manifest["cases"]:
                ids = {case["target"]} | {
                    o["canonical_id"] for o in case["operations"] + case["dependencies"]
                }
                for canonical in sorted(ids):
                    if canonical in manifest["sources"]:
                        continue
                    cur.execute(
                        (
                            "SELECT document_id, canonical_id, relative_path, "
                            "ingestion_id, text FROM ingestion_service.document_nodes "
                            "WHERE repo_id="
                            "%s AND canonical_id=%s"
                        ),
                        (REPOS[case["repo"]], canonical),
                    )
                    source = cur.fetchone()
                    assert source and source["text"], canonical
                    assert str(source["ingestion_id"]) == str(
                        manifest["pins"][case["repo"]]["ingestion_id"]
                    )
                    source["sha256"] = digest(source["text"])
                    manifest["sources"][canonical] = source
                for o in case["operations"] + case["dependencies"]:
                    body = normalized(manifest["sources"][o["canonical_id"]]["text"])
                    for expression in o["expressions"]:
                        assert normalized(expression) in body, (case["id"], expression)
    manifest["local_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    write(path, manifest)
    (DIRECTORY / "manifest.sha256").write_text(
        digest(path.read_text(encoding="utf-8")) + "\n", encoding="utf-8"
    )
    print("Frozen six cases, two diagnostic repositories; no answers inspected")


def label(chunk: dict) -> str:
    metadata = chunk.get("metadata") or {}
    return str(
        chunk.get("canonical_id")
        or metadata.get("canonical_id")
        or metadata.get("source_metadata", {}).get("canonical_id")
        or ""
    )


def coverage(obligations: list[dict], chunks: list[dict]) -> dict:
    details = []
    for item in obligations:
        file_path = item["canonical_id"].split("#")[0]
        eligible = [
            normalized(c["text"])
            for c in chunks
            if label(c) in (item["canonical_id"], file_path)
        ]
        matched = [
            any(normalized(e) in text for text in eligible) for e in item["expressions"]
        ]
        details.append(
            {
                "name": item["name"],
                "satisfied": all(matched),
                "expressions_present": matched,
            }
        )
    return {
        "satisfied": sum(d["satisfied"] for d in details),
        "required": len(details),
        "details": details,
        "scope": "expression-and-source coverage; branch coherence requires review",
    }


def efficiency(case: dict, sources: dict, chunks: list[dict]) -> dict:
    relevant_ids = {case["target"]} | {
        o["canonical_id"] for o in case["operations"] + case["dependencies"]
    }
    covered: set[tuple[str, int]] = set()
    repeated = 0
    for chunk in chunks:
        cid = label(chunk)
        for canonical in relevant_ids:
            if cid not in (canonical, canonical.split("#")[0]):
                continue
            source_lines = sources[canonical]["text"].splitlines()
            for text_line in chunk["text"].splitlines():
                stripped = text_line.strip()
                # Ignore ambiguous common short lines such as return/else/braces.
                if len(stripped) < 12:
                    continue
                matches = [
                    i for i, line in enumerate(source_lines) if line.strip() == stripped
                ]
                if len(matches) != 1:
                    continue
                key = (canonical, matches[0])
                if key in covered:
                    repeated += len(stripped.encode("utf-8"))
                covered.add(key)
    useful = sum(
        len(sources[c]["text"].splitlines()[i].strip().encode("utf-8"))
        for c, i in covered
    )
    return {
        "unique_relevant_bytes_lower_bound": useful,
        "fraction_of_fixed_cap_lower_bound": useful / 4096,
        "repeated_relevant_bytes_lower_bound": repeated,
        "method": (
            "Unique unambiguous nontrivial source lines in frozen relevan"
            "t symbols; excludes whitespace and ambiguous lines"
        ),
    }


def score(case: dict, manifest: dict, record: dict) -> dict:
    plan = record["response"]["retrieval_plan"]
    discovered = case["target"] in set(plan["seed_canonical_ids"]) | set(
        plan["expanded_canonical_ids"]
    )
    target_id = str(manifest["sources"][case["target"]]["document_id"])
    survived = target_id in set(plan["seed_document_ids"]) | set(
        plan["expanded_document_ids"]
    )
    chunks = record["final_chunks"]
    context = record["generation_request"]["context"]
    assert len(context.encode("utf-8")) <= 4096
    assert context == record["assembled_context"]
    assert plan["tokens_after_budget"] == len(context.encode("utf-8"))
    return {
        "target_discovered": discovered,
        "target_survived": survived,
        "operation_coverage": coverage(case["operations"], chunks),
        "dependency_coverage": coverage(case["dependencies"], chunks),
        "efficiency": efficiency(case, manifest["sources"], chunks),
        "delivered_bytes": len(context.encode("utf-8")),
        "context_sha256": digest(context),
        "answer_faithfulness": "pending source-based review; no keyword proxy",
    }


async def check_availability(host: str) -> None:
    import httpx

    preflight = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "scope": "HTTP availability only",
        "services": {},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        for port in (8001, 8002, 8003, 8004):
            try:
                response = await client.get(f"{host}:{port}/version")
                response.raise_for_status()
                preflight["services"][str(port)] = {
                    "available": True,
                    "version": response.json(),
                }
            except httpx.HTTPError as error:
                preflight["services"][str(port)] = {
                    "available": False,
                    "error_type": type(error).__name__,
                }
    write(RESULTS / "availability.json", preflight)
    if not all(s["available"] for s in preflight["services"].values()):
        raise RuntimeError("Application service unavailable; baseline unverified")


def install_observers(service: Any):
    import httpx
    import requests

    original_post = httpx.AsyncClient.post
    original_assemble = service.assemble_context
    original_embed = service.embed_query
    original_sync_request = requests.sessions.Session.request
    observed: dict = {}

    def checkpoint(event: str, **details) -> None:
        RAW.mkdir(parents=True, exist_ok=True)
        record = {
            "at": datetime.now(timezone.utc).isoformat(),
            "case": observed.get("case_id"),
            "event": event,
            **details,
        }
        with (RAW / "capture-events.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(record) + "\n")

    def observe_sync_request(client, method, url, **kwargs):
        # Diagnostic deadline only: the runtime's graph HTTP client otherwise
        # has no deadline and can hide the point at which capture stopped.
        kwargs.setdefault("timeout", (10, 120))
        checkpoint("sync_http_started", method=method, url=str(url))
        response = original_sync_request(client, method, url, **kwargs)
        checkpoint("sync_http_completed", status=response.status_code)
        return response

    async def observe_post(client, url, **kwargs):
        checkpoint("async_http_started", url=str(url))
        observed["last_async_request"] = {"url": str(url), "json": kwargs.get("json")}
        response = await original_post(client, url, **kwargs)
        checkpoint("async_http_completed", url=str(url), status=response.status_code)
        if str(url).endswith("/generate"):
            observed["generation_request"] = kwargs["json"]
            observed["generation_response"] = response.json()
        elif str(url).endswith("/search") or str(url).endswith("/search-by-doc"):
            observed.setdefault("retrieval_requests", []).append(
                {
                    "url": str(url),
                    "request": kwargs.get("json"),
                    "response": response.json(),
                }
            )
        return response

    def observe_assemble(chunks, budget):
        result = original_assemble(chunks, budget)
        if budget <= 4096:
            observed["final_chunks"] = result.chunks
            observed["assembled_context"] = result.text
        return result

    def observe_embed(*arguments, **kwargs):
        result = original_embed(*arguments, **kwargs)
        observed["query_vector"] = result
        return result

    setattr(httpx.AsyncClient, "post", observe_post)
    service.assemble_context = observe_assemble
    service.embed_query = observe_embed
    setattr(requests.sessions.Session, "request", observe_sync_request)

    def restore():
        httpx.AsyncClient.post = original_post
        service.assemble_context = original_assemble
        service.embed_query = original_embed
        requests.sessions.Session.request = original_sync_request

    return observed, checkpoint, restore


def control_inputs(
    manifest: dict, dev_pin: dict, target_document_ids: dict[str, str]
) -> tuple[list[dict], dict, dict]:
    """Retarget the foundry cases to the clean development corpus (#297).

    Returns (cases, pins, sources) as new objects; the frozen manifest is not
    mutated. Only the foundry cases (F1-F3) are replayed. Target document ids
    come from the new repository because the manifest's ids belong to the lost
    generation; the oracle source text is unchanged.
    """
    generation = dev_pin["generation"]
    expected = manifest["pins"]["foundry"]["commit_sha"]
    if generation["ingested_commit_sha"] != expected:
        raise RuntimeError(
            f"dev corpus commit {generation['ingested_commit_sha']} != {expected}"
        )
    cases = [c for c in manifest["cases"] if c["repo"] == "foundry"]
    sources = {k: dict(v) for k, v in manifest["sources"].items()}
    for case in cases:
        target = case["target"]
        if target not in target_document_ids:
            raise RuntimeError(f"target {target} not found in the clean corpus")
        sources[target]["document_id"] = target_document_ids[target]
    pins = {k: dict(v) for k, v in manifest["pins"].items()}
    pins["foundry"].update(
        repo_id=generation["repo_id"], ingestion_id=generation["ingestion_id"]
    )
    return cases, pins, sources


async def baseline(args: argparse.Namespace) -> None:
    await capture(args, "baseline")


async def control(args: argparse.Namespace) -> None:
    await capture(args, "control")


async def capture(args: argparse.Namespace, mode: str) -> None:
    import httpx

    manifest = read(DIRECTORY / "manifest.json")
    assert (
        digest((DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
        == (DIRECTORY / "manifest.sha256").read_text().strip()
    )
    cases = manifest["cases"]
    if mode == "control":
        dev_pin = read(DIRECTORY / "dev-corpus-pin.json")
        targets = {c["target"] for c in cases if c["repo"] == "foundry"}
        async with httpx.AsyncClient(timeout=60) as client:
            lookup = await client.post(
                f"{args.host}:8001/v1/graph/repos/"
                f"{dev_pin['generation']['repo_id']}/nodes/lookup",
                json={"canonical_ids": sorted(targets)},
            )
            lookup.raise_for_status()
        ids = {n["canonical_id"]: n["document_id"] for n in lookup.json()["nodes"]}
        cases, pins, sources = control_inputs(manifest, dev_pin, ids)
        manifest = {**manifest, "pins": pins, "sources": sources}
    await check_availability(args.host)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "rag_orchestrator"))
    config: Any = importlib.import_module("src.core.config")
    from rag_orchestrator.src.core import config as package_config

    settings = config.Settings(
        _env_file=None,
        OLLAMA_BASE_URL=f"{args.host}:11434",
        INGESTION_SERVICE_URL=f"{args.host}:8001",
        VECTOR_STORE_URL=f"{args.host}:8002",
        LLM_SERVICE_URL=f"{args.host}:8003",
    )
    config.get_settings = lambda: settings
    package_config.get_settings = lambda: settings
    service: Any = importlib.import_module("src.core.service")

    observed, checkpoint, restore = install_observers(service)
    logging.disable(logging.CRITICAL)
    try:
        for case in cases:
            path = RAW / f"{mode}-{case['id']}.json"
            if path.exists():
                print(f"{case['id']}: existing baseline preserved", flush=True)
                continue
            observed.clear()
            observed.update(
                {
                    "case_id": case["id"],
                    "mode": mode,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "scope": (
                        "Local unchanged orchestrator with remote read-only HTTP serv"
                        "ices; not original UI or production wire"
                    ),
                    "local_settings": settings.model_dump(mode="json"),
                    "manifest_sha256": digest(
                        (DIRECTORY / "manifest.json").read_text(encoding="utf-8")
                    ),
                }
            )
            pin = manifest["pins"][case["repo"]]
            async with httpx.AsyncClient(timeout=30) as client:
                generation_url = (
                    f"{args.host}:8001/v1/repos/{pin['repo_id']}/generation"
                )
                before = await client.get(generation_url)
                before.raise_for_status()
                observed["generation_before"] = before.json()
                assert before.json()["ingestion_id"] == str(pin["ingestion_id"])
                if mode == "control":
                    assert before.json()["generation_status"] == "ready"
                    assert before.json()["commit_sha"] == pin["commit_sha"]
                observed["versions"] = await fetch_versions(client, args.host)
            print(f"{case['id']}: capturing {mode}", flush=True)
            checkpoint("case_started")
            response = await service.run_rag(
                query=case["query"],
                repo_id=pin["repo_id"],
                top_k=20,
                max_chunks_per_doc=5,
                max_total_tokens=4096,
                model=manifest["model"],
                rerank=False,
                trace_canonical_ids=case_ids(case),
                repository_overview_claim_selection_enabled=False,
                repository_overview_canonical_selection_enabled=False,
                repository_overview_structured_answers_enabled=False,
            )
            observed["response"] = response.model_dump(mode="json")
            async with httpx.AsyncClient(timeout=30) as client:
                after = await client.get(generation_url)
                after.raise_for_status()
                observed["generation_after"] = after.json()
                assert after.json() == observed["generation_before"]
            observed["score"] = score(case, manifest, observed)
            write(path, observed)
            print(
                json.dumps({"case": case["id"], "score": observed["score"]}), flush=True
            )
    finally:
        if observed and "score" not in observed:
            # Preserve observations without giving an incomplete request a score.
            observed["status"] = "incomplete-no-quality-score"
            write(RESULTS / f"incomplete-{mode}-{observed['case_id']}.json", observed)
        restore()


async def fetch_versions(client: Any, host: str) -> dict:
    versions = {}
    for port in (8001, 8002, 8003, 8004):
        version = await client.get(f"{host}:{port}/version")
        version.raise_for_status()
        versions[str(port)] = version.json()
    return versions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "baseline", "control"))
    parser.add_argument("--host", default=os.environ.get("E1_HOST"))
    args = parser.parse_args()
    if args.command != "freeze" and not args.host:
        parser.error("baseline/control need --host or E1_HOST (e.g. http://<host>)")
    if args.command == "freeze":
        freeze()
    elif args.command == "control":
        asyncio.run(control(args))
    else:
        asyncio.run(baseline(args))


if __name__ == "__main__":
    main()
