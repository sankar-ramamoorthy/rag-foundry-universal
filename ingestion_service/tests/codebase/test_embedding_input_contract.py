"""CI-06 (#337): every stored passage is the exact, complete embedding input.

Acceptance criteria covered:
- repository artifacts become exact line windows that cover all artifact
  text and fit the embedding-input contract (character and token budgets);
- the audit's probe: a marker between characters 800 and 900 of a large
  artifact now reaches an embedding input;
- the Ollama embedder never shortens input, asks Ollama not to truncate,
  and records any unavoidable truncation on the affected vector only;
- chunk_text persisted to the vector store equals the text embedded;
- a prior generation built under the legacy contract is not reused.
"""
import os
import random
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import requests

import pytest

from shared.chunks import Chunk
from shared.chunkers.selector import ChunkerFactory
from shared.chunkers.text import TextChunker, estimate_tokens, line_windows
from shared.embedders.input_contract import (
    EMBEDDING_INPUT_CONTRACT,
    EMBEDDING_INPUT_MAX_CHARS,
    EMBEDDING_INPUT_MAX_EST_TOKENS,
)
from shared.embedders.base import EmbeddingInputTooLong
from shared.embedders.ollama import OllamaEmbedder
from shared.embedders.query import embed_query
from src.core.codebase.embedding_buffer import EmbeddingBuffer
from src.api.v1 import codebase_ingest as api
from src.core.http_vectorstore import HttpVectorStore
from src.core.pipeline import IngestionPipeline

pytestmark = pytest.mark.unit


def _tiles(text: str, windows: list[str]) -> list[int]:
    """Assert windows are in-order verbatim slices tiling all of ``text``.

    Window k must start no later than where the covered prefix ends and
    extend past it (after an overflow split it may start before the last
    piece of its predecessor). Returns how many characters each window repeats from its
    predecessor. Picks the furthest valid start, so repeated content in the
    text cannot make a gap look covered.
    """
    if not text:
        assert windows == []
        return []
    assert windows and text.startswith(windows[0])
    start, end, repeated = 0, len(windows[0]), []
    for window in windows[1:]:
        starts = [s for s in range(0, end + 1) if text.startswith(window, s)]
        assert starts, "window is not a contiguous verbatim continuation"
        start = starts[-1]
        assert start + len(window) > end, "window makes no progress"
        repeated.append(end - start)
        end = start + len(window)
    assert end == len(text), "windows stop before the end of the text"
    return repeated


def _random_text(rng: random.Random) -> str:
    alphabet = [
        "def handler(request):\n", "    return self._cache[key]\n", "\n",
        "| a | b | c | d | e | f | g | h |\n", "日本語のテキストです。\n",
        "x" * rng.randint(1, 3000) + "\n", "word " * rng.randint(1, 400),
        "\tindented\r\n", "naïve café\n",
    ]
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 60)))


# ---------------------------------------------------------------------
# line windows
# ---------------------------------------------------------------------

@pytest.mark.parametrize("seed", range(40))
def test_line_windows_cover_text_exactly_within_budgets(seed):
    rng = random.Random(seed)
    text = _random_text(rng)
    windows = line_windows(text, 800, 100, 480)

    _tiles(text, windows)
    for window in windows:
        assert window
        assert len(window) <= 800
        assert estimate_tokens(window) <= 480


def test_line_windows_overlap_repeats_whole_trailing_lines():
    text = "".join(f"line {i:03d} {'x' * 40}\n" for i in range(100))
    windows = line_windows(text, 400, 100)
    assert len(windows) > 1
    for repeated in _tiles(text, windows):
        assert 0 < repeated <= 100
    for previous, current in zip(windows, windows[1:]):
        # The repeated region is whole lines: the next window starts a line.
        assert previous.endswith("\n") and current.startswith("line ")


def test_line_windows_reject_invalid_budgets():
    with pytest.raises(ValueError):
        line_windows("x", 0, 0)
    with pytest.raises(ValueError):
        line_windows("x", 10, 10)
    with pytest.raises(ValueError):
        line_windows("x", 10, 0, 0)


def test_long_prose_line_splits_on_whitespace():
    text = " ".join(f"word{i}" for i in range(400))
    windows = line_windows(text, 800, 0)
    _tiles(text, windows)
    assert all(w.endswith(" ") for w in windows[:-1])


def test_token_budget_bounds_dense_text_the_character_cap_misses():
    cjk = "".join(f"日本語のテキスト{i}です。" for i in range(200))  # ~1 token/char
    table = "".join(f"|{i}|---|---|---|\n" for i in range(100))  # dense
    for text in (cjk, table):
        windows = line_windows(text, 800, 100, 480)
        _tiles(text, windows)
        assert all(estimate_tokens(w) <= 480 for w in windows)


def test_code_artifacts_use_line_windows_at_the_contract_budget():
    chunker, params = ChunkerFactory.choose_strategy("x", source_type="code")
    assert chunker.chunk_strategy == "line_window"
    assert params["chunk_size"] == EMBEDDING_INPUT_MAX_CHARS
    assert params["max_tokens"] == EMBEDDING_INPUT_MAX_EST_TOKENS


def test_audit_probe_marker_reaches_an_embedding_input():
    """The CI-06 reproduction: a marker between characters 800 and 900."""
    lines = [f"    value_{i:04d} = compute({i})\n" for i in range(600)]
    text = "def big():\n" + "".join(lines)
    at = text.index("\n", 820) + 1
    text = text[:at] + "    MARKER_CI06 = 1\n" + text[at:]
    assert 800 < text.index("MARKER_CI06") < 900 and len(text) >= 10000

    chunker, params = ChunkerFactory.choose_strategy(text, source_type="code")
    inputs = [c.content for c in chunker.chunk(text, **params)]
    assert any("MARKER_CI06" in i for i in inputs)
    _tiles(text, inputs)


@pytest.mark.parametrize("length", [500, 5000, 20000])
def test_document_strategies_never_exceed_one_input(length):
    # One unbroken "sentence"/paragraph: previously a single oversized unit.
    text = " ".join(f"word{i}" for i in range(length))[:length]
    chunker, params = ChunkerFactory.choose_strategy(text)
    chunks = chunker.chunk(text, **params)
    assert all(len(c.content) <= EMBEDDING_INPUT_MAX_CHARS for c in chunks)
    covered = [False] * len(text)
    cursor = 0
    for chunk in chunks:
        at = text.find(chunk.content.strip(), cursor)
        assert at != -1
        covered[at:at + len(chunk.content.strip())] = [True] * len(
            chunk.content.strip()
        )
        cursor = at
    assert all(covered[i] for i, ch in enumerate(text) if not ch.isspace())


def test_simple_strategy_rejects_windows_larger_than_the_cap():
    with pytest.raises(ValueError):
        TextChunker(chunk_strategy="simple").chunk(
            "x" * 3000, chunk_size=1000, overlap=100, max_chars=800
        )


# ---------------------------------------------------------------------
# Ollama embedder
# ---------------------------------------------------------------------

# The CI-06 review (R1) counterexamples: each is one passage that fits the
# character and estimated-token budgets, yet mxbai-embed-large (Ollama 0.32)
# rejects it with truncate=false. Live reproduction: test_live_ollama_* below.
REVIEW_OVERFLOW_CASES = {
    "repeated_rare_word": "xyz " * 200,
    "letter_pairs": "qz" * 300,
    "python_comment": "# " + "xyz " * 195 + "TAIL_CI06",
}


def _fake_ollama(calls, rejects=lambda text: len(text) > 1000):
    """Ollama double: rejects inputs for which ``rejects`` holds unless the
    request allows truncation. The rule stands in for the model tokenizer."""

    def post(url, *, json, **kwargs):
        calls.append((list(json["input"]), json["truncate"]))
        resp = MagicMock()
        if not json["truncate"] and any(rejects(t) for t in json["input"]):
            resp.status_code = 400
            resp.text = '{"error":"the input length exceeds the context length"}'
            return resp
        resp.status_code = 200
        resp.json.return_value = {
            "embeddings": [[float(len(t))] for t in json["input"]]
        }
        return resp

    return post


def test_embedder_sends_input_unshortened_and_disables_server_truncation(
    monkeypatch,
):
    calls = []
    monkeypatch.setattr("shared.embedders.ollama.requests.post", _fake_ollama(calls))
    text = "token " * 150  # 900 chars: the legacy client cut this at 800
    chunk = Chunk(chunk_id="c", content=text)

    assert OllamaEmbedder("http://x", "m").embed([chunk]) == [[900.0]]
    assert calls == [([text], False)]
    assert chunk.metadata["embedding_input"] == {
        "contract": EMBEDDING_INPUT_CONTRACT, "truncated": False,
    }


def test_passage_overflow_raises_and_is_never_truncated(monkeypatch):
    calls = []
    monkeypatch.setattr("shared.embedders.ollama.requests.post", _fake_ollama(calls))
    chunks = [Chunk(chunk_id=str(i), content=c)
              for i, c in enumerate(["a" * 10, "b" * 1500, "c" * 20])]

    with pytest.raises(EmbeddingInputTooLong) as raised:
        OllamaEmbedder("http://x", "m", batch_size=10).embed(chunks)

    assert raised.value.positions == [1]
    assert raised.value.vectors == [[10.0], None, [20.0]]
    assert not any(truncate for _, truncate in calls)


def test_overflow_isolation_bisects_instead_of_one_request_per_input(monkeypatch):
    calls = []
    monkeypatch.setattr("shared.embedders.ollama.requests.post", _fake_ollama(calls))
    chunks = [Chunk(chunk_id=str(i), content="ok") for i in range(50)]
    chunks[37].content = "x" * 2000

    with pytest.raises(EmbeddingInputTooLong) as raised:
        OllamaEmbedder("http://x", "m", batch_size=50).embed(chunks)

    assert raised.value.positions == [37]
    assert len(calls) <= 1 + 2 * 6  # one batch, then O(log n) halves


def test_query_overflow_is_truncated_explicitly_and_marked(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr("shared.embedders.ollama.requests.post", _fake_ollama(calls))
    embedder = OllamaEmbedder("http://x", "m")
    vector = embed_query("q" * 1500, embedder)

    assert vector == [1500.0]
    assert embedder.truncated_queries == 1
    assert [inputs for inputs, truncate in calls if truncate] == [["q" * 1500]]
    assert "server-truncated prefix" in caplog.text


def test_other_provider_errors_still_fail(monkeypatch):
    def post(url, json=None, **kwargs):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "model not found"
        return resp

    monkeypatch.setattr("shared.embedders.ollama.requests.post", post)
    with pytest.raises(RuntimeError, match="model not found"):
        OllamaEmbedder("http://x", "m").embed([Chunk(chunk_id="c", content="x")])


# ---------------------------------------------------------------------
# Repository embedding stage: stored passage == embedded input
# ---------------------------------------------------------------------

def _stage(monkeypatch, rejects, *, max_chunks=128):
    """Real pipeline, buffer and record builder over a fake Ollama."""
    calls: list = []
    monkeypatch.setattr(
        "shared.embedders.ollama.requests.post", _fake_ollama(calls, rejects)
    )
    written: list[dict] = []
    store = HttpVectorStore("http://unused")

    def add_vectors(records):
        written.extend(records)

    store.add_vectors = add_vectors
    pipeline = IngestionPipeline(
        validator=Mock(), embedder=OllamaEmbedder("http://x", "m", batch_size=8),
        vector_store=store,
    )
    buffer = EmbeddingBuffer(pipeline, "g", max_chunks=max_chunks, max_bytes=1 << 20)
    return calls, written, pipeline, buffer


def _node(text, document_id="d1"):
    return SimpleNamespace(
        document_id=document_id, canonical_id=f"{document_id}.py#f",
        relative_path=f"{document_id}.py", doc_type="python source", text=text,
    )


def test_persisted_chunk_text_is_exactly_the_embedded_text(monkeypatch):
    calls, written, pipeline, buffer = _stage(monkeypatch, lambda t: len(t) > 10_000)
    body = "".join(f"    step_{i} = run({i})  # {'z' * 30}\n" for i in range(400))
    node = _node("def big():\n" + body)

    api._chunk_and_buffer_node(pipeline, buffer, node, "repo", "ollama")
    buffer.flush()

    stored = [r["metadata"]["chunk_text"] for r in written]
    assert all(truncate is False for _, truncate in calls)
    assert stored == [t for inputs, _ in calls for t in inputs]
    assert [r["metadata"]["chunk_index"] for r in written] == list(range(len(written)))
    _tiles(node.text, stored)
    assert all(
        r["metadata"]["source_metadata"]["embedding_input"]["truncated"] is False
        for r in written
    )


@pytest.mark.parametrize("case", sorted(REVIEW_OVERFLOW_CASES))
def test_review_counterexamples_are_split_not_truncated(monkeypatch, case):
    """R1: a budget-compliant passage the model rejects is split into exact
    pieces, each embedded in full; the stored text equals what was encoded."""
    text = REVIEW_OVERFLOW_CASES[case]
    chunker, params = ChunkerFactory.choose_strategy(text, source_type="code")
    passages = [c.content for c in chunker.chunk(text, **params)]
    assert len(passages) == 1 and estimate_tokens(passages[0]) <= 480

    # Stand-in for the real tokenizer: anything over 300 characters overflows.
    calls, written, pipeline, buffer = _stage(monkeypatch, lambda t: len(t) > 300)
    api._chunk_and_buffer_node(pipeline, buffer, _node(text), "repo", "ollama")
    buffer.flush()

    stored = [r["metadata"]["chunk_text"] for r in written]
    assert stored and all(len(t) <= 300 for t in stored)
    assert not any(truncate for _, truncate in calls)
    assert "".join(stored) == text  # exact pieces, no overlap, nothing lost
    assert [r["metadata"]["chunk_index"] for r in written] == list(range(len(stored)))
    assert all(
        r["metadata"]["source_metadata"]["embedding_input"]["truncated"] is False
        and r["metadata"]["source_metadata"]["overflow_split"] is True
        for r in written
    )
    if case == "python_comment":
        assert stored[-1].endswith("TAIL_CI06")


def test_split_ordinals_stay_consecutive_across_buffer_flushes(monkeypatch):
    """A split in an early flush shifts the same artifact's later ordinals."""
    lines = [f"line_{i:03d} = {'v' * 60}\n" for i in range(60)]
    lines[3] = "OVERFLOW " + "w" * 60 + "\n"
    text = "".join(lines)
    calls, written, pipeline, buffer = _stage(
        monkeypatch, lambda t: "OVERFLOW" in t and len(t) > 40, max_chunks=1
    )
    api._chunk_and_buffer_node(pipeline, buffer, _node(text), "repo", "ollama")
    buffer.flush()

    indices = [r["metadata"]["chunk_index"] for r in written]
    assert indices == list(range(len(written)))
    _tiles(text, [r["metadata"]["chunk_text"] for r in written])
    assert buffer.ordinal_shift["d1"] > 0


def test_unsplittable_overflow_fails_instead_of_storing_a_truncated_vector(
    monkeypatch,
):
    calls, written, pipeline, buffer = _stage(monkeypatch, lambda t: True)
    with pytest.raises(ValueError, match="cannot be split"):
        api._chunk_and_buffer_node(pipeline, buffer, _node("abcd"), "repo", "x")
        buffer.flush()
    assert written == []
    assert not any(truncate for _, truncate in calls)


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("CI06_OLLAMA_URL"),
    reason="set CI06_OLLAMA_URL to an Ollama serving mxbai-embed-large",
)
@pytest.mark.parametrize("case", sorted(REVIEW_OVERFLOW_CASES))
def test_live_ollama_review_counterexamples(case):
    """Live R1 regression against the serving model: the passage is rejected
    strictly, then stored only as pieces the model accepts in full."""
    base = os.environ["CI06_OLLAMA_URL"]
    model = os.environ.get("CI06_OLLAMA_MODEL", "mxbai-embed-large:latest")
    text = REVIEW_OVERFLOW_CASES[case]

    def strict(inputs):
        return requests.post(
            f"{base}/api/embed",
            json={"model": model, "input": inputs, "truncate": False},
            timeout=60,
        )

    assert strict([text]).status_code == 400  # the counterexample still holds

    written: list[dict] = []
    store = HttpVectorStore("http://unused")

    def add_vectors(records):
        written.extend(records)

    store.add_vectors = add_vectors
    pipeline = IngestionPipeline(
        validator=Mock(), embedder=OllamaEmbedder(base, model), vector_store=store,
    )
    buffer = EmbeddingBuffer(pipeline, "g", max_chunks=8, max_bytes=1 << 20)
    api._chunk_and_buffer_node(pipeline, buffer, _node(text), "repo", "ollama")
    buffer.flush()

    stored = [r["metadata"]["chunk_text"] for r in written]
    assert "".join(stored) == text and len(stored) > 1
    for passage in stored:
        assert strict([passage]).status_code == 200, passage[:40]
    assert all(
        not r["metadata"]["source_metadata"]["embedding_input"]["truncated"]
        for r in written
    )


# ---------------------------------------------------------------------
# CI-03 linkage: the reuse gate invalidates legacy-contract vectors
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "prior, expected_match",
    [
        (("heuristic-v1", "ollama:mxbai-embed-large:latest"), False),
        ((ChunkerFactory.VERSION, "ollama:mxbai-embed-large:latest"), False),
        (
            (
                ChunkerFactory.VERSION,
                f"ollama:mxbai-embed-large:latest:{EMBEDDING_INPUT_CONTRACT}",
            ),
            True,
        ),
    ],
)
def test_reuse_gate_rejects_vectors_from_another_input_contract(
    monkeypatch, prior, expected_match,
):
    recorded = {}
    status = Mock()
    status.record_generation_start.side_effect = lambda _id, **kw: recorded.update(kw)
    monkeypatch.setattr(api, "StatusManager", lambda session: status)
    monkeypatch.setattr(
        api, "get_settings",
        lambda: SimpleNamespace(
            EMBEDDING_PROVIDER="ollama", OLLAMA_EMBED_MODEL="mxbai-embed-large:latest"
        ),
    )
    monkeypatch.setattr(api.db_utils, "resolve_current_generation", lambda r: "prior")
    monkeypatch.setattr(api.db_utils, "file_content_hashes", lambda r, g: {"a.py": "h"})
    monkeypatch.setattr(api.db_utils, "generation_config_versions", lambda g: prior)

    _, incremental, _, matches = api._resolve_reuse_eligibility(
        None, uuid.uuid4(), "repo", False
    )
    assert incremental is True
    assert matches is expected_match
    assert recorded["embedding_config_version"].endswith(EMBEDDING_INPUT_CONTRACT)
    assert recorded["chunking_config_version"] == ChunkerFactory.VERSION
    assert ChunkerFactory.VERSION != "heuristic-v1"
