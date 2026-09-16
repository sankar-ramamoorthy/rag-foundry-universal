"""Dependency-free audit probes; no network, database, or production writes.

Run from any directory with Python 3.12+: python <this-file>.
Selected definitions are compiled from the checkout, not reimplemented.
These reproduce current defects; they are not service integration tests.
"""

from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.chunkers.selector import ChunkerFactory  # noqa: E402


def definitions(path, names, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    chosen = [n for n in tree.body if getattr(n, "name", None) in names]
    assert len(chosen) == len(names)
    for node in chosen:
        node.decorator_list = []
    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__", names=[ast.alias(name="annotations")], level=0
            ),
            *chosen,
        ],
        type_ignores=[],
    )
    exec(
        compile(ast.fix_missing_locations(module), str(ROOT / path), "exec"), namespace
    )


log = logging.getLogger("audit")
adapter = {"logger": log}
definitions(
    "rag_orchestrator/src/retrieval/agent_adapter.py",
    {
        "_source_label",
        "build_sources",
        "select_chunks_within_token_budget",
        "build_labeled_context",
        "prepare_chunks_for_agent",
    },
    adapter,
)

# One node can expand far beyond a node-page-size chunk assertion.
chunker, params = ChunkerFactory.choose_strategy("x" * 128_000)
chunks = chunker.chunk("x" * 128_000, **params)
assert len(chunks) == 143
print("node/chunk mismatch: one 128000-character node ->", len(chunks), "chunks")

# Source list still uses the pre-budget list in both service callers.
pool = [
    {"document_id": "seed", "text": "one two", "metadata": {}},
    {"document_id": "helper", "text": "three four", "metadata": {}},
]
context, _ = adapter["build_labeled_context"](pool, 2)
sources = adapter["build_sources"](pool)
assert "helper" in sources and "helper" not in context
print("source overstatement:", sources, "but prompt contains only seed")

# The actual simple-service call supplies seed-only document_order.
retrieved = SimpleNamespace(
    chunks_by_document={
        doc: [
            SimpleNamespace(
                document_id=doc, chunk_id=doc, text=doc, metadata={}, score=1.0
            )
        ]
        for doc in ("seed", "expanded")
    }
)
selected = adapter["prepare_chunks_for_agent"](retrieved, document_order=["seed"])
assert [c["document_id"] for c in selected] == ["seed"]
print("simple-RAG assembly: fetched expanded document omitted by seed-only order")

# Storage returns true index 14; orchestrator overwrites it with response position 0.
service = {
    "RetrievedChunk": lambda **kw: SimpleNamespace(**kw),
    "canonical_id_from_metadata": lambda m: "file.py#f",
    "doc_type_from_metadata": lambda m: "function",
}
definitions(
    "rag_orchestrator/src/core/service.py",
    {"_add_chunks", "_apply_doc_type_tie_break"},
    service,
)
added = service["_add_chunks"](
    "d", [{"chunk_id": "c", "text": "body", "metadata": {"chunk_index": 14}}], set(), {}
)
assert added[0].chunk_index == 0
print("trace index mismatch: stored index 14 -> reported index", added[0].chunk_index)

# Relaxed HNSW results need an explicit score-order contract before this helper.
unordered = [
    SimpleNamespace(score=score, doc_type=kind)
    for score, kind in [(0.9, "markdown"), (0.5, "markdown"), (0.89, "function")]
]
chosen = service["_apply_doc_type_tie_break"](unordered, 1, 0.02, {"function"})
assert chosen[0].doc_type == "markdown"
print("near-tie helper: out-of-order low score hides a qualifying implementation")

# Lost node mapping makes a retry unable to finish ingestion-request cleanup.
state = {"nodes": True, "request": True}


class Session:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def delete_nodes(repo_id):
    state["nodes"] = False
    return 1


def fail_request_cleanup(ids):
    raise RuntimeError("simulated failure after graph commit")


delete = {
    "logger": log,
    "SessionLocal": Session,
    "get_settings": lambda: SimpleNamespace(VECTOR_STORE_SERVICE_URL="unused"),
    "HttpVectorStore": lambda **kw: SimpleNamespace(
        delete_by_ingestion_id=lambda i: None
    ),
    "CodebaseGraphPersistence": lambda **kw: SimpleNamespace(
        delete_repo_nodes=delete_nodes
    ),
    "RepoDeleteResponse": lambda **kw: SimpleNamespace(**kw),
    "db_utils": SimpleNamespace(
        list_ingestion_ids_for_repo=lambda repo: ["i"] if state["nodes"] else [],
        delete_ingestion_requests=fail_request_cleanup,
    ),
}
definitions("ingestion_service/src/api/v1/repos.py", {"delete_repo"}, delete)
try:
    asyncio.run(delete["delete_repo"]("repo"))
except RuntimeError as exc:
    assert "after graph commit" in str(exc)
else:
    raise AssertionError("expected cleanup failure")
retry = asyncio.run(delete["delete_repo"]("repo"))
assert retry.status == "not_found" and state["request"]
print("delete retry: not_found while ingestion request remains")

# Splitting one artifact between calls resets persisted chunk ordinals.
store_ns = {"logger": log}
definitions(
    "ingestion_service/src/core/http_vectorstore.py", {"HttpVectorStore"}, store_ns
)
store = store_ns["HttpVectorStore"]("unused")
records = []
store.add_vectors = lambda batch: records.extend(batch)
for piece in chunks[:2]:
    store.persist_batch([piece], [[0.0]], "i", ["d"])
assert [r["metadata"]["chunk_index"] for r in records] == [0, 0]
print(
    "split-artifact persistence: chunk indices [0, 0]; "
    "bounded calls need ordinal continuity"
)
print("7 audit probes reproduced the expected current behavior")
