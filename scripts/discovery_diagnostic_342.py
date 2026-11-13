"""Issue #342: retrieval-only A/B/C discovery diagnostic for the Step 0 question.

Compares, on the unchanged Step 0 question and the unchanged ingested
generation, whether existing mechanisms can *discover* the implementation
of the POST /v1/rag -> vector retrieval path without being told which
functions to look for:

  A  vector seed search (reused from the #351 capture; no new model call)
  B  existing query-mention extractors, plus identifier-token discovery over
     the exported graph with terms taken mechanically from the question
  C  graph-first: resolve the route named in the question, then traverse
     (deployed GET /v1/repos/{id}/trace, the existing expansion policy, and
     one declared counterfactual placeholder-resolution rule)

Everything is read-only HTTP: graph export, the deployed /trace endpoint and
vector-store search-by-doc for stored text. No generation, no SQL, no writes.

The TARGETS / HOPS tables below are the reviewed ground truth (verified
against commit 8e06335, the ingested commit). They are used ONLY to score
results after each mechanism has run; no mechanism receives them as input.

    python scripts/discovery_diagnostic_342.py STEP0.json CANDIDATES_351.json \
        --host http://HOST --out RAW/2026-11-12-342-abc-discovery.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "discovery_diagnostic_342.v1"
SEED_K = 20  # current seed search k; the bound for "discovered" in A and B
PATH_ROLE_EXCLUDE = re.compile(
    r"(^|/)(tests?|examples?|reproduce|benchmarks?|evaluation|fixtures)(/|$)"
)

ORCH = "rag_orchestrator/src/core/service.py"
TARGETS = {
    "route": "route:rag_orchestrator:POST:/v1/rag",
    "rag_endpoint": "rag_orchestrator/src/api/v1/routes.py#rag_endpoint",
    "run_rag": f"{ORCH}#run_rag",
    "resolve_repo_id_http": f"{ORCH}#resolve_repo_id_http",
    "get_embedder": "shared/embedders/factory.py#get_embedder",
    "OllamaEmbedder": "shared/embedders/ollama.py#OllamaEmbedder",
    "embed_query": "shared/embedders/query.py#embed_query",
    "OllamaEmbedder.embed": "shared/embedders/ollama.py#OllamaEmbedder.embed",
    "hybrid_retrieve": f"{ORCH}#hybrid_retrieve",
    "_query_generation": f"{ORCH}#_query_generation",
    "vector_route": "route:vector_store_service:POST:/v1/vectors/search",
    "similarity_search": "vector_store_service/src/api/v1/vectors.py#similarity_search",
    "PgVectorStore.similarity_search": (
        "vector_store_service/src/core/vectorstore/pgvector_store.py"
        "#PgVectorStore.similarity_search"
    ),
}

# (id, from, to, kind, source-witness regex in the caller's stored text).
# `to` is a TARGETS key, or None for an endpoint outside the repository.
# kind: route | direct | indirect (function passed as a value) | dispatch
# (call through an abstract-typed parameter) | http | sql
HOPS: list[tuple[str, str, str | None, str, str]] = [
    ("H1", "route", "rag_endpoint", "route", r""),
    ("H2", "rag_endpoint", "run_rag", "direct", r"\brun_rag\("),
    ("H3", "run_rag", "resolve_repo_id_http", "direct", r"resolve_repo_id_http\("),
    ("H4", "resolve_repo_id_http", None, "http", r"/v1/repos\b"),
    ("H5", "run_rag", "get_embedder", "direct", r"get_embedder\("),
    ("H6", "get_embedder", "OllamaEmbedder", "direct", r"OllamaEmbedder\("),
    ("H7", "run_rag", "embed_query", "indirect", r"to_thread\(\s*embed_query"),
    ("H8", "embed_query", "OllamaEmbedder.embed", "dispatch", r"embedder\.embed\("),
    ("H9", "OllamaEmbedder.embed", None, "http", r"/api/embed"),
    ("H10", "run_rag", "hybrid_retrieve", "direct", r"hybrid_retrieve\("),
    ("H11", "hybrid_retrieve", "_query_generation", "direct", r"_query_generation\("),
    ("H12", "_query_generation", None, "http", r"/generation"),
    ("H13", "hybrid_retrieve", "vector_route", "http", r"/v1/vectors/search"),
    ("H14", "vector_route", "similarity_search", "route", r""),
    (
        "H15",
        "similarity_search",
        "PgVectorStore.similarity_search",
        "indirect",
        r"store\.similarity_search",
    ),
    ("H16", "PgVectorStore.similarity_search", None, "sql", r"<=>"),
]


def host_from_env() -> str:
    env = dict(
        line.split("=", 1)
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    match = re.match(r"(https?://[^:/]+)", env["REMOTE_OLLAMA_BASE_URL"].strip())
    if not match:
        raise SystemExit("REMOTE_OLLAMA_BASE_URL not set")
    return match.group(1)


def import_orchestrator():
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "rag_orchestrator"))
    # Settings read `.env` from the working directory at import time; the
    # repo-root `.env` holds keys the orchestrator's Settings rejects.
    cwd = os.getcwd()
    os.chdir(ROOT / "rag_orchestrator")
    try:
        import src.retrieval.codebase_queries as cq
        import src.retrieval.exact_source_preservation as esp
        import src.retrieval.named_symbol_first as nsf
        import src.retrieval.trace_impact as ti
        import src.retrieval.traversal_selector as ts
    finally:
        os.chdir(cwd)
    return cq, esp, nsf, ti, ts


def build_graph(cq, data: dict, repo_id: str):
    """The existing loader's validation and construction, without its HTTP."""
    cq._validate_graph_snapshot(data, repo_id, data["ingestion_id"])
    graph = cq.CodebaseGraph()
    graph.repo_id, graph.ingestion_id = repo_id, data["ingestion_id"]
    for node in data["nodes"]:
        graph.add_node(cq.Node(node["canonical_id"], node["relative_path"]))
    for src, edges in data["relationships"].items():
        for e in edges:
            graph.add_edge(
                src,
                e["to_canonical_id"],
                e["relation_type"],
                e["relationship_metadata"],
            )
    return graph


# ---------------------------------------------------------------- arm A


def arm_a(cand: dict) -> dict:
    seeds = cand["seed_searches"][0]["results"]
    witnesses = {w["canonical_id"]: w for w in cand["witnesses"]}
    ranks = {}
    for key, cid in TARGETS.items():
        w = witnesses.get(cid)
        ranks[key] = (
            None
            if w is None
            else {
                "best_score": w["best_score"],
                "rank": w["best_score_position"]["rank"],
                "beyond_deep_k": w["best_score_position"]["beyond_deep_k"],
            }
        )
    return {
        "source": "reused from the #351 retrieval-candidates capture",
        "seed_k": len(seeds),
        "seed_doc_types": Counter(str(s["doc_type"]) for s in seeds),
        "seed_labels": [s["label"] for s in seeds],
        "pre_budget_pool_doc_types": Counter(
            str(c["doc_type"]) for c in cand["pre_budget_pool"]
        ),
        "target_ranks": ranks,
        "discovered": sorted(
            k for k, r in ranks.items() if r and r["rank"] and r["rank"] <= SEED_K
        ),
    }


# ---------------------------------------------------------------- arm B


def tokens(text: str) -> list[str]:
    # The existing orchestrator tokenizer (_rank_expanded_canonical_ids),
    # applied after splitting identifiers on '_' and camelCase.
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text).replace("_", " ")
    return re.findall(r"[a-z0-9]+", text.lower())


def identifier_discovery(query: str, nodes: list[dict], scope: str) -> dict:
    """IDF-weighted overlap between question tokens and canonical-id tokens.
    No stopword list or chosen terms: IDF over the scoped nodes does the
    weighting, and a token absent from every identifier contributes nothing."""

    def in_scope(n: dict) -> bool:
        cid = n["canonical_id"]
        if scope == "all":
            return True
        if "#" not in cid or "source" not in n["doc_type"]:
            return False
        return scope == "source" or not PATH_ROLE_EXCLUDE.search(n["relative_path"])

    scoped = [n for n in nodes if in_scope(n)]
    node_tokens = {n["canonical_id"]: set(tokens(n["canonical_id"])) for n in scoped}
    df = Counter(t for ts_ in node_tokens.values() for t in ts_)
    q = set(tokens(query))
    total = len(scoped)
    idf = {t: math.log(total / df[t]) for t in q if df.get(t)}
    scored = sorted(
        (
            (sum(idf.get(t, 0.0) for t in q & ts_), cid)
            for cid, ts_ in node_tokens.items()
        ),
        key=lambda x: (-x[0], x[1]),
    )
    scored = [s for s in scored if s[0] > 0]
    rank_of = {}
    for i, (score, cid) in enumerate(scored, 1):
        rank_of.setdefault(cid, i)
    return {
        "scope": scope,
        "scoped_nodes": total,
        "query_tokens_with_idf": dict(sorted(idf.items(), key=lambda kv: -kv[1])),
        "query_tokens_absent_from_identifiers": sorted(q - set(idf)),
        "top": [
            {"rank": i, "score": round(s, 3), "cid": c}
            for i, (s, c) in enumerate(scored[:SEED_K], 1)
        ],
        "target_ranks": {k: rank_of.get(cid) for k, cid in TARGETS.items()},
    }


def arm_b(query: str, data: dict, graph, esp, nsf, ts) -> dict:
    symbols = sorted(
        {c.split("#", 1)[1].rsplit(".", 1)[-1] for c in graph.nodes if "#" in c}
    )
    existing = {
        "traversal_selector._extract_mentioned_methods": sorted(
            map(list, ts._extract_mentioned_methods(query))
        ),
        "exact_source_preservation._targets": esp._targets(query),
        "named_symbol_first._is_named over graph symbol names": [
            s for s in symbols if len(s) > 2 and nsf._is_named(s, query)
        ],
        "traversal_selector.select_traversal_strategies": [
            ts._relation_type_of(s)
            for s in ts.select_traversal_strategies(query, set())
        ],
    }
    variants = [
        identifier_discovery(query, data["nodes"], s)
        for s in ("all", "source", "path_role")
    ]
    for v in variants:
        v["discovered"] = sorted(
            k for k, r in v["target_ranks"].items() if r is not None and r <= SEED_K
        )
    return {"existing_mention_extractors": existing, "identifier_discovery": variants}


# ---------------------------------------------------------------- arm C


ROUTE_IN_QUERY = re.compile(r"\b(GET|POST|PUT|DELETE|PATCH)\s+(/[\w/{}.-]*)")


def route_anchors(query: str, graph) -> list[dict]:
    out = []
    for method, path in ROUTE_IN_QUERY.findall(query):
        suffix = f":{method}:{path.rstrip('/.')}"
        matches = sorted(
            c for c in graph.nodes if c.startswith("route:") and c.endswith(suffix)
        )
        out.append({"method": method, "path": path, "matches": matches})
    return out


def deployed_trace(
    client: httpx.Client, host: str, repo_id: str, start: str, rels: str
) -> dict:
    resp = client.get(
        f"{host}:8004/v1/repos/{repo_id}/trace",
        params={"start": start, "relation_types": rels, "direction": "forward"},
        timeout=180,
    )
    body = resp.json()
    hops = body.get("hops", []) if resp.status_code == 200 else []
    reached = {h["canonical_id"]: h["hop_index"] for h in hops}
    return {
        "start": start,
        "relation_types": rels,
        "status": resp.status_code,
        "ingestion_id": body.get("ingestion_id"),
        "hop_count": len(hops),
        "truncated": body.get("truncated"),
        "depth_limited": body.get("depth_limited"),
        "gaps_total": len(body.get("gaps", [])),
        "first_hops": [
            [
                h["hop_index"],
                h["relation_type"],
                h["parent_canonical_id"],
                h["canonical_id"],
            ]
            for h in hops[:12]
        ],
        "target_hop_index": {k: reached.get(cid) for k, cid in TARGETS.items()},
        "error": None if resp.status_code == 200 else body,
    }


def existing_expansion(query: str, graph, ts, seeds: set[str], cap: int) -> dict:
    """The current hybrid_retrieve expansion policy (strategies + per-seed
    traversal + explicit-mention hop + ordering), seeded with the
    route-resolved handler instead of vector seeds."""
    strategies = ts.select_traversal_strategies(query, seeds)
    cands = ts.execute_traversals_from_seeds_detailed(graph, seeds, strategies)
    cands = cands + ts.expand_mentioned_methods(graph, query, cands, seeds)
    terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    cands.sort(
        key=lambda c: (
            c.strategy_index,
            -len(terms & set(re.findall(r"[a-z0-9]+", c.node.canonical_id.lower()))),
        )
    )
    ranked = [c.node.canonical_id for c in cands if c.node.canonical_id not in seeds]
    ranked = list(dict.fromkeys(ranked))
    resolvable = [
        c for c in ranked if not c.startswith(("EXTERNAL_", "route:", "compose:"))
    ]
    return {
        "seeds": sorted(seeds),
        "strategies": [ts._relation_type_of(s) for s in strategies],
        "expanded_total": len(ranked),
        "expanded_resolvable": len(resolvable),
        "max_expanded_docs": cap,
        "expanded_first": ranked[:cap],
        "target_positions": {
            k: (ranked.index(cid) + 1 if cid in ranked else None)
            for k, cid in TARGETS.items()
        },
    }


SRC_PLACEHOLDER = re.compile(r"^EXTERNAL_SYMBOL:src\.([\w.]+)\.(\w+)$")


def resolve_src_placeholder(graph, caller: str, placeholder: str) -> str | None:
    """Counterfactual rule: a service-local absolute import `src.a.b.f` called
    from `<service>/src/...` names `<service>/src/a/b.py#f`."""
    m = SRC_PLACEHOLDER.match(placeholder)
    if not m or "/src/" not in caller:
        return None
    service = caller.split("/src/", 1)[0]
    cid = f"{service}/src/{m.group(1).replace('.', '/')}.py#{m.group(2)}"
    return cid if cid in graph.nodes else None


def counterfactual_reach(
    graph, start: str, max_depth: int, follow_service: bool
) -> dict:
    """Local BFS over HANDLED_BY/CALL edges (and optionally CALLS_SERVICE ->
    EXPOSES_ENDPOINT), additionally following src.-rooted placeholders via
    `resolve_src_placeholder`. Diagnostic only: shows what one resolution
    rule, or service-edge following, would make reachable."""
    rels = {"HANDLED_BY", "CALL"} | (
        {"CALLS_SERVICE", "EXPOSES_ENDPOINT"} if follow_service else set()
    )
    depth = {start: 0}
    via = {}
    queue = deque([start])
    resolved_placeholders = []
    while queue:
        cur = queue.popleft()
        if depth[cur] >= max_depth:
            continue
        node = graph.get_node(cur)
        for rel, nbrs in node.out_edges.items():
            if rel not in rels:
                continue
            for n in sorted(nbrs, key=lambda x: x.canonical_id):
                nxt = n.canonical_id
                if nxt.startswith("EXTERNAL_SYMBOL:"):
                    r = resolve_src_placeholder(graph, cur, nxt)
                    if r is None:
                        continue
                    resolved_placeholders.append([cur, nxt, r])
                    nxt = r
                if nxt not in depth:
                    depth[nxt] = depth[cur] + 1
                    via[nxt] = [cur, rel]
                    queue.append(nxt)
    return {
        "start": start,
        "follow_service_edges": follow_service,
        "max_depth": max_depth,
        "reachable_nodes": len(depth) - 1,
        "resolved_placeholders": resolved_placeholders,
        "target_depth": {k: depth.get(cid) for k, cid in TARGETS.items()},
        "target_parent": {k: via.get(cid) for k, cid in TARGETS.items()},
    }


# ---------------------------------------------------------------- hop scoring


def hop_representation(graph, frm: str, to: str | None, kind: str) -> dict:
    node = graph.get_node(frm)
    if node is None:
        return {"graph": "caller_missing"}
    out = {rel: {n.canonical_id for n in ns} for rel, ns in node.out_edges.items()}
    if to is not None:
        for rel in ("HANDLED_BY", "CALL"):
            if to in out.get(rel, set()):
                return {"graph": "exact", "relation": rel}
    if to is not None and to.startswith("route:"):
        svc = to.split(":")[1]
        hits = [c for c in out.get("CALLS_SERVICE", set()) if c.endswith(f"#{svc}")]
        if hits:
            routes = sorted(
                {
                    r.canonical_id
                    for h in hits
                    for r in graph.get_node(h).out_edges.get("EXPOSES_ENDPOINT", set())
                }
            )
            return {
                "graph": "service_level",
                "calls_service": hits,
                "service_route_fanout": len(routes),
                "target_route_among_them": to in routes,
            }
    name = (to or "").split("#")[-1].rsplit(".", 1)[-1]
    placeholders = sorted(
        c
        for c in out.get("CALL", set())
        if c.startswith("EXTERNAL_SYMBOL:")
        and name
        and c.rsplit(".", 1)[-1].split(":")[-1] == name
    )
    if placeholders:
        return {"graph": "placeholder", "placeholders": placeholders}
    if kind in ("http", "sql"):
        return {
            "graph": "service_level" if out.get("CALLS_SERVICE") else "absent",
            "calls_service": sorted(out.get("CALLS_SERVICE", set())),
        }
    return {"graph": "absent"}


def stored_texts(
    client, host, repo_id, generation, qvec, doc_ids: dict[str, str]
) -> dict:
    texts = {}
    for key, doc in doc_ids.items():
        resp = client.post(
            f"{host}:8002/v1/vectors/search-by-doc",
            json={
                "document_id": doc,
                "k": 100,
                "query_vector": qvec,
                "ingestion_id": generation,
                "repo_id": repo_id,
            },
            timeout=60,
        )
        resp.raise_for_status()  # a 422 must not read as "no witness"
        rows = resp.json().get("results", [])
        rows.sort(key=lambda r: (r.get("metadata") or {}).get("chunk_index", 0))
        texts[key] = "\n".join(str(r.get("text", "")) for r in rows)
    return texts


# ---------------------------------------------------------------- main


def run(args) -> dict:
    step0 = json.loads(args.step0.read_text(encoding="utf-8"))
    cand = json.loads(args.candidates.read_text(encoding="utf-8"))
    content = step0["application_input"]["messages"][1]["content"]
    query = content.rsplit("Question:\n", 1)[1].strip()
    repo_id, generation = step0["repo_id"], step0["generation_id"]
    host = args.host or host_from_env()
    cq, esp, nsf, ti, ts = import_orchestrator()

    with httpx.Client(timeout=60) as client:
        before = client.get(f"{host}:8001/v1/repos/{repo_id}/generation").json()
        if (
            before.get("ingestion_id") != generation
            or before.get("generation_status") != "ready"
        ):
            raise SystemExit(f"generation changed or not ready: {before}")
        versions = {
            p: client.get(f"{host}:{p}/version").json() for p in (8001, 8002, 8004)
        }
        resp = client.get(
            f"{host}:8001/v1/graph/repos/{repo_id}",
            params={"expected_generation_id": generation},
            timeout=180,
        )
        resp.raise_for_status()
        data = resp.json()
        graph = build_graph(cq, data, repo_id)

        anchors = route_anchors(query, graph)
        route_cids = [m for a in anchors for m in a["matches"]]
        handlers = {
            n.canonical_id
            for r in route_cids
            for n in graph.get_node(r).out_edges.get("HANDLED_BY", set())
        }
        traces = [
            deployed_trace(client, host, repo_id, r, rels)
            for r in route_cids
            for rels in (
                "HANDLED_BY,CALL",
                "HANDLED_BY,CALL,CALLS_SERVICE,EXPOSES_ENDPOINT",
            )
        ]

        doc_of = {n["canonical_id"]: n["document_id"] for n in data["nodes"]}
        callers = {h[1] for h in HOPS if h[4]}
        texts = stored_texts(
            client,
            host,
            repo_id,
            generation,
            cand["query_vector"],
            {k: doc_of[TARGETS[k]] for k in callers if TARGETS[k] in doc_of},
        )
        after = client.get(f"{host}:8001/v1/repos/{repo_id}/generation").json()

    hops = []
    for hid, frm, to, kind, pattern in HOPS:
        rep = hop_representation(
            graph, TARGETS[frm], TARGETS.get(to) if to else None, kind
        )
        text = texts.get(frm, "")
        hops.append(
            {
                "hop": hid,
                "from": frm,
                "to": to or "(outside repository)",
                "kind": kind,
                **rep,
                "source_witness": (bool(re.search(pattern, text)) if pattern else None),
                "caller_stored_bytes": len(text.encode("utf-8")) if pattern else None,
            }
        )

    return {
        "schema": SCHEMA,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "scope": "read-only HTTP: graph export, deployed /trace, vector search-by-doc; "
        "no generation, no SQL, no writes",
        "git_head": os.popen("git rev-parse HEAD").read().strip(),
        "service_versions": versions,
        "repo_id": repo_id,
        "generation_before": before,
        "generation_after": after,
        "generation_unchanged": before == after,
        "graph_ingestion_id": data["ingestion_id"],
        "graph_counts": {
            "nodes": data["total_nodes"],
            "edges": dict(
                Counter(
                    e["relation_type"]
                    for v in data["relationships"].values()
                    for e in v
                )
            ),
        },
        "query": query,
        "targets": TARGETS,
        "A_vector": arm_a(cand),
        "B_lexical_symbol": arm_b(query, data, graph, esp, nsf, ts),
        "C_graph": {
            "route_anchors": anchors,
            "handlers": sorted(handlers),
            "deployed_trace": traces,
            "existing_expansion_from_handler": existing_expansion(
                query, graph, ts, handlers, args.max_expanded_docs
            ),
            "counterfactual_src_placeholder_rule": [
                counterfactual_reach(graph, r, 6, follow)
                for r in route_cids
                for follow in (False, True)
            ],
        },
        "hops": hops,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("step0", type=Path)
    p.add_argument("candidates", type=Path)
    p.add_argument(
        "--host", help="scheme://host; default from REMOTE_OLLAMA_BASE_URL in .env"
    )
    p.add_argument("--max-expanded-docs", type=int, default=20)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    data = run(args)
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({"generation_unchanged": data["generation_unchanged"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
