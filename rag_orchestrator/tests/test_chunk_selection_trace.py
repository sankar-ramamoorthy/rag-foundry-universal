"""Synthetic contracts for issue #254; no repository-specific answers."""

import pytest

from rag_orchestrator.src.retrieval.agent_adapter import (
    assemble_context,
    prepare_chunks_for_agent,
)
from rag_orchestrator.src.retrieval.chunk_selection_trace import SelectionTrace
from rag_orchestrator.src.retrieval.execute_plan import execute_retrieval_plan
from rag_orchestrator.src.retrieval.types import RetrievedChunk, RetrievedContext
from shared.retrieval.retrieval_plan import RetrievalPlan

pytestmark = pytest.mark.unit


def chunks(doc, count):
    return [RetrievedChunk(
        chunk_id=f"{doc}-{i}", document_id=doc, text="body", score=1.0,
        metadata={}, canonical_id=doc, chunk_index=i, fetch_position=i,
    ) for i in range(count)]


def test_global_stop_attributes_unvisited_three_chunk_document():
    documents = {f"d{i}": chunks(f"d{i}", 5) for i in range(10)}
    documents["target"] = chunks("target", 3)
    context = RetrievedContext(documents)
    order = list(documents)
    trace = SelectionTrace({"target"})
    seen = []

    def filter_chunk(chunk):
        seen.append(chunk.chunk_id)
        return True

    result = prepare_chunks_for_agent(
        context, document_order=order, selection_trace=trace,
        filter_chunk=filter_chunk,
    )
    baseline = prepare_chunks_for_agent(context, document_order=order)
    assert result == baseline
    assert len(result) == 50
    assert len(seen) == 50  # tail filters must not run for instrumentation
    assert len(trace.rows) == 3
    assert {r["rule"] for r in trace.rows} == {"max_total_chunks"}
    assert all(r["limit"] == r["consumed"] == 50 for r in trace.rows)
    assert all(r["evaluated"] is False for r in trace.rows)
    assert [r["position"] for r in trace.rows] == [0, 1, 2]
    assert all(r["document_position"] == 10 for r in trace.rows)
    assert all("text" not in r for r in trace.rows)


def test_plan_slice_records_first_loss_and_preserves_output():
    documents = {"target": chunks("target", 7)}
    plan = RetrievalPlan(seed_document_ids={"target"})
    trace = SelectionTrace({"target"})
    result = execute_retrieval_plan(
        plan=plan, retrieved_chunks_by_document=documents,
        top_k_per_document=5, selection_trace=trace,
    )
    baseline = execute_retrieval_plan(
        plan=plan, retrieved_chunks_by_document=documents, top_k_per_document=5,
    )
    assert result == baseline
    assert [r["chunk_index"] for r in trace.rows] == [5, 6]
    assert all(r["stage"] == "execute_plan" for r in trace.rows)
    prepare_chunks_for_agent(result, selection_trace=trace, max_chunks_per_doc=2)
    assert [r["chunk_index"] for r in trace.rows] == [5, 6, 2, 3, 4]
    assert [r["stage"] for r in trace.rows] == [
        "execute_plan", "execute_plan", "agent_adapter", "agent_adapter",
        "agent_adapter",
    ]


def test_filter_and_early_stop_are_different():
    context = RetrievedContext({"target": chunks("target", 4)})
    trace = SelectionTrace({"target"})
    result = prepare_chunks_for_agent(
        context, max_total_chunks=1, selection_trace=trace,
        filter_chunk=lambda chunk: chunk.chunk_index != 0,
    )
    assert [c["chunk_index"] for c in result] == [1]
    assert [r["rule"] for r in trace.rows] == [
        "filter_chunk", "max_total_chunks", "max_total_chunks",
    ]
    assert [r["evaluated"] for r in trace.rows] == [True, False, False]


def test_byte_budget_records_actual_cost_and_keeps_later_small_chunk():
    trace = SelectionTrace({"target"})
    values: list[dict[str, object]] = [
        {"canonical_id": "target", "document_id": "d", "chunk_id": "large",
         "text": "x" * 80},
        {"canonical_id": "target", "document_id": "d", "chunk_id": "small",
         "text": "ok"},
    ]
    result = assemble_context(values, 40, selection_trace=trace)
    assert result == assemble_context(values, 40)
    assert result.chunks == [values[1]]
    assert trace.rows[0]["rule"] == "context_bytes"
    assert trace.rows[0]["cost"] > 40
    assert trace.rows[0]["consumed"] == 0


@pytest.mark.parametrize("stage", ["rerank", "overview_policy"])
def test_later_exclusion_is_not_called_a_count_or_byte_loss(stage):
    chunk = {"canonical_id": "target", "document_id": "d", "chunk_id": "c"}
    trace = SelectionTrace({"target"})
    trace.removed([chunk], [], stage)
    trace.removed([chunk], [], "later_stage")
    assert len(trace.rows) == 1
    assert trace.rows[0]["stage"] == stage
    assert trace.rows[0]["limit"] is None


def test_untracked_chunk_does_not_create_trace_row():
    trace = SelectionTrace({"other"})
    context = RetrievedContext({"target": chunks("target", 2)})
    prepare_chunks_for_agent(context, max_chunks_per_doc=1, selection_trace=trace)
    assert trace.rows == []


def test_adapter_token_stop_does_not_evaluate_unvisited_tail():
    trace = SelectionTrace({"target"})
    context = RetrievedContext({"target": chunks("target", 3)})
    counted = []

    def cost(chunk):
        counted.append(chunk.chunk_index)
        return 5

    result = prepare_chunks_for_agent(
        context, max_tokens=5, chunk_token_count=cost, selection_trace=trace,
    )
    assert [c["chunk_index"] for c in result] == [0]
    assert counted == [0, 1]
    assert [r["evaluated"] for r in trace.rows] == [True, False]
    assert all(r["rule"] == "adapter_tokens" for r in trace.rows)
    assert all(r["consumed"] == 5 for r in trace.rows)
