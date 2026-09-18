"""#160 worker-level bounds, lifetime and output-parity regression tests."""

from types import SimpleNamespace
from unittest.mock import Mock
import weakref

import pytest

from src.api.v1 import codebase_ingest as api
from src.core.config import Settings
from src.core.pipeline import IngestionPipeline
from src.core.http_vectorstore import HttpVectorStore


pytestmark = pytest.mark.unit


class Page(list):
    pass


class Pages:
    def __init__(self, texts, progress):
        self.texts = texts
        self.progress = progress
        self.scans = 0

    def iter_artifact_pages(
        self, repo, attempt, *, page_size, max_artifact_bytes, expected_nodes
    ):
        assert self.progress  # Stage was persisted before preflight/first page.
        assert (repo, attempt) == ("repo", "attempt")
        assert expected_nodes == len(self.texts)
        self.scans += 1
        for start in range(0, len(self.texts), page_size):
            page = Page(
                SimpleNamespace(
                    document_id=f"d{i}",
                    canonical_id=f"m{i}.py#f",
                    relative_path=f"m{i}.py",
                    doc_type="FUNCTION",
                    text=self.texts[i],
                )
                for i in range(start, min(start + page_size, len(self.texts)))
            )
            assert all(len((r.text or "").encode()) <= max_artifact_bytes for r in page)
            reference = weakref.ref(page)
            yield page
            del page
            assert reference() is None, "Caller retained previous page into next fetch"


def run_stage(texts, *, batch_size=7, max_bytes=7000, fail_after=None):
    records, progress, batches = [], [], []
    store = HttpVectorStore("http://unused")

    def write(batch):
        if fail_after is not None and len(batches) >= fail_after:
            raise RuntimeError("write fixture failed")
        batches.append(len(batch))
        records.extend(batch)

    store.add_vectors = write
    store.delete_by_ingestion_id = lambda ingestion_id: None
    embedder = Mock()
    embedder.embed.side_effect = lambda items: [[float(len(c.content))] for c in items]
    pipeline = IngestionPipeline(
        validator=Mock(), embedder=embedder, vector_store=store
    )
    persistence = Pages(texts, progress)
    settings = Settings(
        _env_file=None,
        DATABASE_URL="unused",
        INGESTION_NODE_PAGE_SIZE=1,
        INGESTION_EMBED_BATCH_SIZE=batch_size,
        INGESTION_EMBED_MAX_BYTES=max_bytes,
    )
    error = None
    try:
        result = api._embed_repo_artifacts(
            pipeline,
            persistence,
            "repo",
            "attempt",
            len(texts),
            "mock",
            settings,
            lambda state: progress.append(dict(state)),
        )
    except RuntimeError as exc:
        error = exc
        result = None
    return result, records, progress, batches, pipeline, persistence, error


@pytest.mark.parametrize("batch_size", [1, 7, 128])
def test_paged_stage_large_node_parity_and_progress(batch_size):
    texts = [None, "\t\n\u2003", "x" * 128000, "def f(): return 1"]
    result, records, progress, batches, pipeline, persistence, error = run_stage(
        texts,
        batch_size=batch_size,
    )
    assert error is None
    assert persistence.scans == 2
    assert result == (len(records), 0)
    assert max(batches) <= batch_size
    expected = []
    for i, content in enumerate(texts):
        if not (content or "").strip():
            continue
        for index, chunk in enumerate(pipeline._chunk(content, "code", "mock")):
            expected.append((f"d{i}", index, chunk.content))
    actual = [
        (
            r["metadata"]["document_id"],
            r["metadata"]["chunk_index"],
            r["metadata"]["chunk_text"],
        )
        for r in records
    ]
    assert actual == expected
    for record in records:
        metadata = record["metadata"]["source_metadata"]
        assert metadata["language"] == "python"
        assert metadata["repo_id"] == "repo"
        assert metadata["doc_type"] == "FUNCTION"
        assert metadata["canonical_id"] == metadata["source_metadata"]["canonical_id"]
    assert progress[0]["stage"] == "embedding"
    assert progress[-1]["nodes_total"] == progress[-1]["nodes_processed"] == 2
    assert progress[-1]["chunks_persisted"] == len(records)
    for key in ("nodes_processed", "chunks_persisted"):
        assert [p[key] for p in progress] == sorted(p[key] for p in progress)
    assert progress[-1]["max_buffer_chunks"] <= batch_size
    assert progress[-1]["max_buffer_bytes"] <= 7000


def test_empty_stage_does_not_embed_and_reports_zero():
    result, records, progress, _, pipeline, _, error = run_stage([])
    assert error is None and result == (0, 0) and not records
    pipeline._embedder.embed.assert_not_called()
    assert all(value == 0 for key, value in progress[-1].items() if key != "stage")


def test_write_failure_leaves_prior_acknowledgements_without_claiming_completion():
    _, records, progress, _, _, _, error = run_stage(["x" * 128000], fail_after=2)
    assert error is not None
    assert len(records) == 14
    assert progress[-1]["chunks_persisted"] == 14
    assert all(p["stage"] != "completed" for p in progress)


def test_background_worker_releases_builder_and_graph_before_embedding(monkeypatch):
    references = []

    class Graph:
        relationships = []

        def all_entities(self):
            return [{"text": "fixture"}]

    class Builder:
        def __init__(self, **kwargs):
            references.append(weakref.ref(self))

        def build(self):
            graph = Graph()
            references.append(weakref.ref(graph))
            return graph

    session, status, persistence = Mock(), Mock(), Mock()
    persistence.persist_graph.return_value = {"nodes": 1}
    monkeypatch.setattr(api, "SessionLocal", lambda: session)
    monkeypatch.setattr(api, "StatusManager", lambda session: status)
    monkeypatch.setattr(api, "CodebaseGraphPersistence", lambda session: persistence)
    monkeypatch.setattr(api, "RepoGraphBuilder", Builder)
    monkeypatch.setattr(api, "_build_pipeline", lambda provider: Mock())

    def embed(**kwargs):
        assert len(references) == 2 and all(ref() is None for ref in references)
        assert "nodes" not in kwargs and kwargs["expected_nodes"] == 1
        return 1, 0

    embedding = Mock(side_effect=embed)
    monkeypatch.setattr(api, "_embed_repo_artifacts", embedding)
    api._background_ingest_repo(api.uuid4(), None, ".", "mock")
    embedding.assert_called_once()
    status.mark_failed.assert_not_called()
    status.mark_completed.assert_called_once()
    assert [
        call.args[1]["stage"] for call in status.update_embed_progress.call_args_list
    ] == ["graph_build", "graph_persist"]
