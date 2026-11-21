# rag_orchestrator/src/core/citations.py
"""
Structured citations (issue #407, specs/012-structured-citations).

One citation per passage that entered the final context, built from the
final-context manifest the pipeline already returns. Line ranges are null with
a stated reason until ingestion persists definition spans; nothing is dropped
and nothing is guessed.
"""

from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel

RANGE_REASON = "line span not persisted at ingestion"


class Citation(BaseModel):
    repo_id: str
    generation_id: Optional[str] = None
    path: Optional[str] = None
    canonical_id: Optional[str] = None
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    text_sha256: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    range_reason: Optional[str] = RANGE_REASON


def _text(value: Any) -> Optional[str]:
    return str(value) if value else None


def from_manifest(
    repo_id: str,
    generation_id: Optional[str],
    manifest: Optional[Sequence[Mapping[str, Any]]],
) -> list[Citation]:
    return [
        Citation(
            repo_id=repo_id,
            generation_id=generation_id,
            path=_text(entry.get("relative_path")),
            canonical_id=_text(entry.get("canonical_id")),
            document_id=_text(entry.get("document_id")),
            chunk_id=_text(entry.get("chunk_id")),
            text_sha256=_text(entry.get("text_sha256")),
        )
        for entry in (manifest or [])
    ]


def from_inventory(
    repo_id: str, plan: Mapping[str, Any], sources: Sequence[str]
) -> list[Citation]:
    """The inventory path inspects one whole file; cite it with the verified
    whole-file digest. Anything not verified complete cites nothing."""
    if plan.get("completion") != "verified_complete" or not sources:
        return []
    return [
        Citation(
            repo_id=repo_id,
            generation_id=plan.get("generation_id"),
            path=sources[0],
            text_sha256=plan.get("returned_text_sha256"),
        )
    ]
