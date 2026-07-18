# ingestion_service/tests/codebase/test_batch_embedding.py
"""
F-08 (WP-S2): batch embedding + persistence.

Acceptance criteria covered:
- vector-store HTTP calls scale with batches, not artifacts:
  ingesting N chunks issues ceil(N/500) POSTs to /v1/vectors/batch,
  asserted via a request counter on a test double;
- exactly one canonical_id -> document_id query per repo ingest
  (per-node get_node_by_canonical_id is no longer called);
- OllamaEmbedder honors batch_size: one /api/embed POST per batch,
  order of embeddings preserved across batches.
"""
from unittest.mock import patch, MagicMock

import pytest

from shared.chunks import Chunk
from shared.embedders.ollama import OllamaEmbedder
from src.core.http_vectorstore import HttpVectorStore
from src.core.pipeline import IngestionPipeline
from src.api.v1.codebase_ingest import _embed_repo_artifacts

pytestmark = pytest.mark.unit


def _make_chunks(n: int) -> list[Chunk]:
    return [Chunk(chunk_id=f"c{i}", content=f"text {i}") for i in range(n)]


# ---------------------------------------------------------------------
# OllamaEmbedder batching
# ---------------------------------------------------------------------

def _ollama_response(texts_per_call):
    """Build a fake requests.post that echoes one embedding per input."""
    def fake_post(url, json=None, **kwargs):
        texts_per_call.append(list(json["input"]))
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "embeddings": [[float(len(t))] for t in json["input"]]
        }
        return resp
    return fake_post


def test_ollama_embedder_splits_into_batches():
    calls: list[list[str]] = []
    embedder = OllamaEmbedder(base_url="http://x", model="m", batch_size=50)
    chunks = _make_chunks(120)

    with patch(
        "shared.embedders.ollama.requests.post", side_effect=_ollama_response(calls)
    ):
        embeddings = embedder.embed(chunks)

    assert [len(c) for c in calls] == [50, 50, 20]
    assert len(embeddings) == 120
    # order preserved: embedding i encodes len("text i")
    assert embeddings[0] == [float(len("text 0"))]
    assert embeddings[119] == [float(len("text 119"))]


def test_ollama_embedder_single_batch_when_small():
    calls: list[list[str]] = []
    embedder = OllamaEmbedder(base_url="http://x", model="m", batch_size=50)

    with patch(
        "shared.embedders.ollama.requests.post", side_effect=_ollama_response(calls)
    ):
        embeddings = embedder.embed(_make_chunks(3))

    assert len(calls) == 1
    assert len(embeddings) == 3


def test_ollama_embedder_empty_input_no_http():
    embedder = OllamaEmbedder(base_url="http://x", model="m", batch_size=50)
    with patch("shared.embedders.ollama.requests.post") as post:
        assert embedder.embed([]) == []
    post.assert_not_called()


def test_ollama_embedder_count_mismatch_raises():
    def bad_post(url, json=None, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"embeddings": [[1.0]]}  # always one
        return resp

    embedder = OllamaEmbedder(base_url="http://x", model="m", batch_size=50)
    with patch("shared.embedders.ollama.requests.post", side_effect=bad_post):
        with pytest.raises(RuntimeError):
            embedder.embed(_make_chunks(2))


# ---------------------------------------------------------------------
# HttpVectorStore.persist_batch
# ---------------------------------------------------------------------

def test_persist_batch_slices_http_calls():
    store = HttpVectorStore(base_url="http://vs")
    batches: list[list[dict]] = []
    store.add_vectors = lambda records: batches.append(records)

    n = 1200
    chunks = _make_chunks(n)
    embeddings = [[0.0]] * n
    document_ids = [f"doc-{i % 7}" for i in range(n)]

    store.persist_batch(chunks, embeddings, "ing-1", document_ids)

    assert [len(b) for b in batches] == [500, 500, 200]


def test_persist_batch_per_chunk_document_id_and_index():
    store = HttpVectorStore(base_url="http://vs")
    batches: list[list[dict]] = []
    store.add_vectors = lambda records: batches.append(records)

    chunks = _make_chunks(4)
    document_ids = ["doc-a", "doc-a", "doc-b", "doc-a"]
    store.persist_batch(chunks, [[0.0]] * 4, "ing-1", document_ids)

    records = [r for b in batches for r in b]
    assert [r["metadata"]["document_id"] for r in records] == document_ids
    # chunk_index restarts per document
    assert [r["metadata"]["chunk_index"] for r in records] == [0, 1, 0, 2]
    assert all(r["metadata"]["ingestion_id"] == "ing-1" for r in records)


def test_persist_batch_length_mismatch_raises():
    store = HttpVectorStore(base_url="http://vs")
    with pytest.raises(ValueError):
        store.persist_batch(_make_chunks(2), [[0.0]] * 2, "ing-1", ["doc-a"])


def test_persist_batch_empty_no_http():
    store = HttpVectorStore(base_url="http://vs")
    calls = []
    store.add_vectors = lambda records: calls.append(records)
    store.persist_batch([], [], "ing-1", [])
    assert calls == []


# ---------------------------------------------------------------------
# _embed_repo_artifacts: whole-repo batch stage
# ---------------------------------------------------------------------

class CountingPersistence:
    """Test double: one map query allowed, per-node lookups forbidden."""

    def __init__(self, mapping: dict):
        self.mapping = mapping
        self.map_queries = 0

    def get_canonical_id_map(self, repo_id: str) -> dict:
        self.map_queries += 1
        return dict(self.mapping)

    def get_node_by_canonical_id(self, repo_id, canonical_id):
        raise AssertionError(
            "per-node get_node_by_canonical_id must not be called (F-08)"
        )


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    def embed(self, chunks):
        self.calls += 1
        return [[0.0]] * len(chunks)


class NoOpValidator:
    def validate(self, text):
        return None


def _make_nodes(n: int) -> list[dict]:
    return [
        {
            "canonical_id": f"pkg/mod{i}.py",
            "relative_path": f"pkg/mod{i}.py",
            "doc_type": "code",
            "text": f"def f{i}():\n    return {i}\n",
        }
        for i in range(n)
    ]


def _run_stage(nodes, mapping, batch_size=500):
    store = HttpVectorStore(base_url="http://vs")
    http_calls: list[int] = []
    store.add_vectors = lambda records: http_calls.append(len(records))
    store.PERSIST_BATCH_SIZE = batch_size  # instance attr shadows class default

    embedder = FakeEmbedder()
    pipeline = IngestionPipeline(
        validator=NoOpValidator(), embedder=embedder, vector_store=store
    )
    persistence = CountingPersistence(mapping)

    counts = _embed_repo_artifacts(
        pipeline=pipeline,
        persistence=persistence,
        repo_id="repo-1",
        ingestion_id="ing-1",
        nodes=nodes,
        provider="mock",
    )
    return counts, persistence, embedder, http_calls


def test_embed_repo_artifacts_batches_and_single_map_query():
    nodes = _make_nodes(30)
    mapping = {n["canonical_id"]: f"doc-{i}" for i, n in enumerate(nodes)}

    (chunk_count, skipped), persistence, embedder, http_calls = _run_stage(
        nodes, mapping
    )

    assert persistence.map_queries == 1
    assert embedder.calls == 1  # one embed pass over all chunks
    assert skipped == 0
    assert chunk_count >= 30  # at least one chunk per node
    # N chunks -> ceil(N/500) HTTP calls; 30 small nodes fit in one
    assert len(http_calls) == 1
    assert sum(http_calls) == chunk_count


def test_embed_repo_artifacts_http_calls_scale_with_batches():
    nodes = _make_nodes(25)
    mapping = {n["canonical_id"]: f"doc-{i}" for i, n in enumerate(nodes)}

    # force tiny persist batches to observe slicing without 500+ nodes
    (chunk_count, _), _, _, http_calls = _run_stage(nodes, mapping, batch_size=10)

    expected_calls = -(-chunk_count // 10)  # ceil
    assert len(http_calls) == expected_calls
    assert sum(http_calls) == chunk_count


def test_embed_repo_artifacts_skips_textless_and_unmapped_nodes():
    nodes = _make_nodes(3)
    nodes.append({"canonical_id": "pkg/empty.py", "text": "   "})
    nodes.append(
        {
            "canonical_id": "pkg/ghost.py",
            "relative_path": "pkg/ghost.py",
            "doc_type": "code",
            "text": "def g():\n    return 0\n",
        }
    )
    mapping = {n["canonical_id"]: f"doc-{i}" for i, n in enumerate(nodes[:3])}

    (chunk_count, skipped), _, embedder, http_calls = _run_stage(nodes, mapping)

    assert skipped == 1  # ghost.py had no DB record
    assert chunk_count >= 3
    assert sum(http_calls) == chunk_count


def test_embed_repo_artifacts_injects_canonical_metadata():
    nodes = _make_nodes(2)
    mapping = {n["canonical_id"]: f"doc-{i}" for i, n in enumerate(nodes)}

    store = HttpVectorStore(base_url="http://vs")
    received: list[dict] = []
    store.add_vectors = lambda records: received.extend(records)

    pipeline = IngestionPipeline(
        validator=NoOpValidator(), embedder=FakeEmbedder(), vector_store=store
    )
    _embed_repo_artifacts(
        pipeline=pipeline,
        persistence=CountingPersistence(mapping),
        repo_id="repo-1",
        ingestion_id="ing-1",
        nodes=nodes,
        provider="mock",
    )

    assert received
    for record in received:
        meta = record["metadata"]["source_metadata"]
        assert meta["repo_id"] == "repo-1"
        assert meta["canonical_id"] in mapping
        assert record["metadata"]["document_id"] == mapping[meta["canonical_id"]]
        assert meta["source_metadata"]["canonical_id"] == meta["canonical_id"]
