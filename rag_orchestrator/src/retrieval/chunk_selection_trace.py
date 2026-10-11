"""Request-local first-loss accounting for already retrieved tracked chunks."""

from typing import Any

from .types import RetrievedChunk


class SelectionTrace:
    def __init__(self, canonical_ids: set[str]):
        self.canonical_ids = canonical_ids
        self.rows: list[dict[str, Any]] = []
        self._seen: set[tuple[str, str]] = set()

    def record(
        self, chunk: RetrievedChunk | dict[str, Any], *, stage: str, rule: str,
        position: int, document_position: int | None = None,
        limit: int | None = None, consumed: int | None = None,
        evaluated: bool = True, cost: int | None = None,
    ) -> None:
        def value(key: str) -> Any:
            return chunk.get(key) if isinstance(chunk, dict) else getattr(chunk, key)

        if value("canonical_id") not in self.canonical_ids:
            return
        key = (str(value("document_id")), str(value("chunk_id")))
        if key in self._seen:
            return
        self._seen.add(key)
        self.rows.append({
            **{name: value(name) for name in (
                "canonical_id", "document_id", "chunk_id", "chunk_index",
                "fetch_position",
            )},
            "stage": stage, "rule": rule, "position": position,
            "document_position": document_position, "limit": limit,
            "consumed": consumed, "evaluated": evaluated, "cost": cost,
        })

    def stopped_tail(
        self, documents: dict[str, list[RetrievedChunk]], order: list[str],
        document_position: int, next_position: int, *, rule: str,
        limit: int, consumed: int,
    ) -> None:
        # Observe unvisited identities only. Never run filters/token callbacks.
        for doc_pos in range(document_position, len(order)):
            start = next_position if doc_pos == document_position else 0
            for pos, chunk in enumerate(documents.get(order[doc_pos], [])):
                if pos >= start:
                    self.record(
                        chunk, stage="agent_adapter", rule=rule, position=pos,
                        document_position=doc_pos, limit=limit, consumed=consumed,
                        evaluated=False,
                    )

    def removed(
        self, before: list[dict[str, Any]], after: list[dict[str, Any]], stage: str,
    ) -> None:
        retained = {(c.get("document_id"), c.get("chunk_id")) for c in after}
        for position, chunk in enumerate(before):
            if (chunk.get("document_id"), chunk.get("chunk_id")) not in retained:
                self.record(chunk, stage=stage, rule=stage, position=position)


def record(trace: SelectionTrace | None, chunk: Any, **details: Any) -> None:
    if trace is not None:
        trace.record(chunk, **details)


def record_slice(
    trace: SelectionTrace | None, chunks: list[RetrievedChunk], kept: int,
    **details: Any,
) -> None:
    if trace is not None:
        for position in range(kept, len(chunks)):
            trace.record(chunks[position], position=position, consumed=kept, **details)


def record_tail(trace: SelectionTrace | None, *args: Any, **details: Any) -> None:
    if trace is not None:
        trace.stopped_tail(*args, **details)


def record_removed(trace: SelectionTrace | None, *args: Any) -> None:
    if trace is not None:
        trace.removed(*args)


def attach_trace(trace: SelectionTrace | None, plan: dict[str, Any]) -> None:
    if trace is not None:
        plan["chunk_selection_trace"] = trace.rows
