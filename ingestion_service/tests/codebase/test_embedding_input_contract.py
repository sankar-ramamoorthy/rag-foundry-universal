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
import random
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from shared.chunks import Chunk
from shared.chunkers.selector import ChunkerFactory
from shared.chunkers.text import TextChunker, estimate_tokens, line_windows
from shared.embedders.input_contract import (
    EMBEDDING_INPUT_CONTRACT,
    EMBEDDING_INPUT_MAX_CHARS,
    EMBEDDING_INPUT_MAX_EST_TOKENS,
)
from shared.embedders.ollama import OllamaEmbedder
from src.api.v1 import codebase_ingest as api
from src.core.http_vectorstore import HttpVectorStore
from src.core.pipeline import IngestionPipeline

pytestmark = pytest.mark.unit


def _tiles(text: str, windows: list[str]) -> list[int]:
    """Assert windows are in-order verbatim slices tiling all of ``text``.

    Window k must start inside window k-1 (or exactly where it ends) and
    extend past it. Returns how many characters each window repeats from its
    predecessor. Picks the furthest valid start, so repeated content in the
    text cannot make a gap look covered.
    """
    if not text:
        assert windows == []
        return []
    assert windows and text.startswith(windows[0])
    start, end, repeated = 0, len(windows[0]), []
    for window in windows[1:]:
        starts = [s for s in range(start + 1, end + 1) if text.startswith(window, s)]
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

def _fake_ollama(calls, context_chars=1000):
    """Ollama double: rejects inputs over context_chars unless truncating."""

    def post(url, *, json, **kwargs):
        calls.append((list(json["input"]), json["truncate"]))
        resp = MagicMock()
        too_long = any(len(t) > context_chars for t in json["input"])
        if not json["truncate"] and too_long:
            resp.status_code = 400
            resp.text = '{"error":"the input length exceeds the context length"}'
            return resp
        resp.status_code = 200
        resp.json.return_value = {
            "embeddings": [[float(min(len(t), context_chars))] for t in json["input"]]
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


def test_overflow_is_isolated_and_recorded_on_that_vector_only(monkeypatch):
    calls = []
    monkeypatch.setattr("shared.embedders.ollama.requests.post", _fake_ollama(calls))
    chunks = [Chunk(chunk_id=str(i), content=c)
              for i, c in enumerate(["a" * 10, "b" * 1500, "c" * 20])]
    embedder = OllamaEmbedder("http://x", "m", batch_size=10)

    assert embedder.embed(chunks) == [[10.0], [1000.0], [20.0]]
    assert [c.metadata["embedding_input"]["truncated"] for c in chunks] == [
        False, True, False,
    ]
    assert embedder.truncated_inputs == 1
    # Only the offender is ever sent with server-side truncation enabled.
    assert [inputs for inputs, truncate in calls if truncate] == [["b" * 1500]]


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

def test_persisted_chunk_text_is_exactly_the_embedded_text(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "shared.embedders.ollama.requests.post", _fake_ollama(calls, 10_000)
    )
    written: list[dict] = []
    store = HttpVectorStore("http://unused")

    def add_vectors(records):
        written.extend(records)

    store.add_vectors = add_vectors
    pipeline = IngestionPipeline(
        validator=Mock(), embedder=OllamaEmbedder("http://x", "m"), vector_store=store,
    )
    body = "".join(f"    step_{i} = run({i})  # {'z' * 30}\n" for i in range(400))
    node = SimpleNamespace(
        document_id="d1", canonical_id="big.py#big", relative_path="big.py",
        doc_type="python source", text="def big():\n" + body,
    )

    class Buffer:
        def append(self, chunk, document_id, ordinal):
            pipeline.embed_and_persist_batch(
                chunks=[chunk], ingestion_id="g", document_ids=[document_id],
                chunk_indices=[ordinal],
            )

    api._chunk_and_buffer_node(pipeline, Buffer(), node, "repo", "ollama")

    embedded = [text for inputs, _ in calls for text in inputs]
    stored = [r["metadata"]["chunk_text"] for r in written]
    assert stored == embedded
    assert [r["metadata"]["chunk_index"] for r in written] == list(range(len(written)))
    _tiles(node.text, stored)
    assert all(
        r["metadata"]["source_metadata"]["embedding_input"]["truncated"] is False
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
