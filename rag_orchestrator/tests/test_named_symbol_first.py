import ast
import inspect
import re
from pathlib import Path

from src.retrieval import named_symbol_first as nsf
from src.retrieval.agent_adapter import assemble_context
from src.retrieval.exact_source_preservation import prioritize_exact_sources
from src.retrieval.named_symbol_first import promote_named_symbol_chunks

SERVICE = Path(__file__).resolve().parents[1] / "src/core/service.py"


def _c(label: str, text: str = "body", i: int = 0) -> dict:
    return {
        "canonical_id": label,
        "document_id": label,
        "chunk_id": f"{label}:{i}",
        "chunk_index": i,
        "text": text,
    }


POOL = [
    _c("a/x.py#helper"),
    _c("a/y.py#run_rag"),
    _c("docs/guide.md#run_rag"),
    _c("a/z.py#other"),
    _c("a/y.py#run_rag", "second", 1),
]


def test_named_symbol_chunks_come_first_and_only_order_changes():
    out, trace = promote_named_symbol_chunks(POOL, "What does run_rag do?")
    assert [c["chunk_id"] for c in out[:2]] == [
        "a/y.py#run_rag:0",
        "a/y.py#run_rag:1",
    ]
    assert sorted(map(id, out)) == sorted(map(id, POOL))
    # stable within the rest
    assert [c["chunk_id"] for c in out[2:]] == [
        "a/x.py#helper:0",
        "docs/guide.md#run_rag:0",
        "a/z.py#other:0",
    ]
    assert trace["promoted_chunk_count"] == 2
    assert trace["promoted_labels"] == ["a/y.py#run_rag"]


def test_nothing_named_returns_same_list_object():
    out, trace = promote_named_symbol_chunks(POOL, "how does the pipeline work")
    assert out is POOL
    assert trace["promoted_chunk_count"] == 0


def test_whole_token_case_sensitive_and_method_names():
    pool = [_c("a.py#Agent.run"), _c("b.py#run"), _c("c.py#get")]
    first = promote_named_symbol_chunks(pool, "call run now")[0][0]
    assert first["canonical_id"] == "b.py#run"
    first = promote_named_symbol_chunks(pool, "Agent.run")[0][0]
    assert first["canonical_id"] == "a.py#Agent.run"
    assert promote_named_symbol_chunks(pool, "RUN")[0] is pool
    assert promote_named_symbol_chunks(pool, "running gets")[0] is pool
    assert promote_named_symbol_chunks(pool, "xrun_")[0] is pool


def test_several_named_symbols_promoted_in_pool_order():
    pool = [_c("a.py#z"), _c("b.py#alpha"), _c("c.py#beta"), _c("d.py#q")]
    out, _ = promote_named_symbol_chunks(pool, "beta then alpha")
    assert [c["canonical_id"] for c in out] == [
        "b.py#alpha", "c.py#beta", "a.py#z", "d.py#q",
    ]


def test_labels_without_hash_or_non_python_never_promoted():
    pool = [_c("README.md#run"), _c("a.rs#run"), _c("plain"), _c("a.py#")]
    assert promote_named_symbol_chunks(pool, "run plain")[0] is pool


def test_label_read_from_metadata_like_the_capture_code():
    chunk = {"metadata": {"source_metadata": {"canonical_id": "a.py#f"}}, "text": "t"}
    other = {"canonical_id": "b.py#g", "text": "t"}
    assert promote_named_symbol_chunks([other, chunk], "f")[0][0] is chunk


def test_promotion_changes_what_the_budget_keeps_but_not_the_chunks():
    big = _c("a.py#other", "x" * 200)
    target = _c("b.py#target", "t" * 100)
    pool = [big, target]
    assert target not in assemble_context(pool, 250).chunks
    out, _ = promote_named_symbol_chunks(pool, "target")
    assert target in assemble_context(out, 250).chunks


def test_function_signature_takes_only_chunks_and_query():
    assert list(inspect.signature(promote_named_symbol_chunks).parameters) == [
        "chunks",
        "query",
    ]
    tree = ast.parse(inspect.getsource(nsf))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    }
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert {getattr(i, "module", None) or i.names[0].name for i in imports} == {
        "re",
        "typing",
    }
    for forbidden in ("manifest", "get_settings", "trace_canonical_ids", "case_id"):
        assert not any(forbidden in n for n in names)


def test_output_order_is_what_the_exact_source_stage_passes_through():
    # With the stage disabled (the experiment's configuration) it is a no-op,
    # so the allocator sees the mechanism's order.
    out, _ = promote_named_symbol_chunks(POOL, "run_rag")
    same, trace = prioritize_exact_sources(out, "run_rag", 100, enabled=False)
    assert same is out and trace == {}


def test_service_call_site_pins_the_integration_invariant():
    source = SERVICE.read_text(encoding="utf-8")
    assert "enabled=claim_type == \"repository_overview\" and claim_selection" in source
    assert "named_symbol_first: bool = False" in source
    flag = source.index("agent_chunks = _order_named_symbol_first(")
    pool_call = source.index("assemble_context(agent_chunks, 2**63)")
    exact = source.index("agent_chunks, preservation_trace = prioritize_exact_sources(")
    budgeted = source.index("assemble_context(agent_chunks, context_budget)")
    assert pool_call < flag < exact < budgeted
    block = source[flag:exact]
    assert len(re.findall(r"agent_chunks", block)) == 2  # reassignment and call only


# --- Development-pool check (F1-F3 only; spec section 7) -------------------
import json  # noqa: E402

import pytest  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
_DEV_RAW = _ROOT / "DOCS/test_results/_raw/code-evidence-e1"
_DEV_MANIFEST = _ROOT / "DOCS/evaluations/code-evidence-e1/manifest.json"
_CAP = 4096


def _dev_case(case_id: str):
    path = _DEV_RAW / f"control-pool-{case_id}.json"
    if not path.exists() or not _DEV_MANIFEST.exists():
        pytest.skip("raw development captures are absent (git-ignored)")
    capture = json.loads(path.read_text(encoding="utf-8"))
    case = next(
        c
        for c in json.loads(_DEV_MANIFEST.read_text(encoding="utf-8"))["cases"]
        if c["id"] == case_id
    )
    return case, capture["pre_budget_chunks"], capture["final_chunks"]


def _target_count(chunks: list[dict], target: str) -> int:
    return sum(1 for c in chunks if nsf.chunk_label(c) == target)


@pytest.mark.parametrize(
    ("case_id", "before", "after"), [("F1", 3, 3), ("F2", 0, 3), ("F3", 0, 3)]
)
def test_development_pools_match_the_275_counterfactual(case_id, before, after):
    case, pool, control_final = _dev_case(case_id)
    target = case["target"]
    # The unpromoted budgeted pass reproduces the recorded control context.
    control = assemble_context(pool, _CAP).chunks
    assert [c["chunk_id"] for c in control] == [c["chunk_id"] for c in control_final]
    assert _target_count(control, target) == before
    promoted, trace = promote_named_symbol_chunks(pool, case["query"])
    assert trace["promoted_chunk_count"] >= after
    assert sorted(map(id, promoted)) == sorted(map(id, pool))
    final = assemble_context(promoted, _CAP).chunks
    assert _target_count(final, target) == after


# --- run_rag integration: default off is inert, on only reorders ----------
import asyncio  # noqa: E402
import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import httpx  # noqa: E402
import test_wp_t1d_final_context_manifest as _fixture  # noqa: E402
from src.core.service import run_rag  # noqa: E402

from rag_orchestrator.src.retrieval import codebase_utils  # noqa: E402


def _run(monkeypatch, query: str, budget: int, **kwargs):
    monkeypatch.setattr(
        httpx, "AsyncClient", _fixture._patched_client(_fixture.FakeBackend())
    )
    monkeypatch.setattr(
        codebase_utils, "get_cached_graph", lambda repo_id: _fixture._build_graph()
    )

    async def fake_resolve(repo_id):
        return repo_id or "repo-x"

    monkeypatch.setattr("src.core.service.resolve_repo_id_http", fake_resolve)
    monkeypatch.setattr("src.core.service.embed_query", lambda q, e: [0.0] * 8)
    monkeypatch.setattr("src.core.service.get_embedder", lambda **kw: object())
    return asyncio.run(
        run_rag(query=query, repo_id="repo-x", max_total_tokens=budget, **kwargs)
    )


def _delivered(result) -> list[str]:
    return [e["canonical_id"] for e in result.retrieval_plan["final_context_manifest"]]


def _strip(value, drop=("trace_id", "named_symbol_first")):
    """Drop per-call random ids (and the diagnostic key) before comparing."""
    if isinstance(value, dict):
        return {k: _strip(v, drop) for k, v in value.items() if k not in drop}
    if isinstance(value, list):
        return [_strip(v, drop) for v in value]
    return value


def _comparable(result) -> dict:
    return _strip(result.model_dump(mode="json"))


@pytest.mark.parametrize("budget", [60, 80, 4096])
@pytest.mark.parametrize("query", ["explain the module", "explain helper"])
def test_default_off_is_identical_to_the_pre_change_behavior(
    monkeypatch, query, budget
):
    default = _run(monkeypatch, query, budget)
    explicit = _run(monkeypatch, query, budget, named_symbol_first=False)
    assert "named_symbol_first" not in default.retrieval_plan
    assert _strip(default.model_dump(mode="json"), ("trace_id",)) == _strip(
        explicit.model_dump(mode="json"), ("trace_id",)
    )


def test_on_with_nothing_named_changes_nothing_but_the_diagnostic(monkeypatch):
    off = _run(monkeypatch, "explain the module", 80)
    on = _run(monkeypatch, "explain the module", 80, named_symbol_first=True)
    assert on.retrieval_plan["named_symbol_first"]["promoted_chunk_count"] == 0
    assert _comparable(on) == _comparable(off)


def test_on_with_a_named_symbol_changes_only_which_chunk_the_budget_keeps(
    monkeypatch,
):
    off = _run(monkeypatch, "explain helper", 80)
    on = _run(monkeypatch, "explain helper", 80, named_symbol_first=True)
    assert _delivered(off) == ["module.py"]
    assert _delivered(on) == ["helper.py#helper"]
    assert on.retrieval_plan["named_symbol_first"] == {
        "enabled": True,
        "promoted_labels": ["helper.py#helper"],
        "promoted_chunk_count": 1,
    }
    # The pool is unchanged: the unbounded token count is the same.
    assert (
        on.retrieval_plan["tokens_before_budget"]
        == off.retrieval_plan["tokens_before_budget"]
    )
