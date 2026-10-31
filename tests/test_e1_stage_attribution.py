"""#275: stage attribution of a target symbol from a pool-capturing control run."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "attribution", ROOT / "scripts/e1_stage_attribution.py"
)
assert SPEC is not None and SPEC.loader is not None
attribution = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(attribution)

TARGET = "src/a.py#target"


def chunk(cid, size, score=0.5, doc=None):
    return {
        "canonical_id": cid,
        "document_id": doc or cid,
        "chunk_id": f"{cid}:{size}:{score}",
        "text": "x" * size,
        "score": score,
    }


def capture(pool, final, *, seeds=(TARGET,), expanded=(), fetched=True, budget=4096):
    return {
        "response": {
            "retrieval_plan": {
                "seed_canonical_ids": list(seeds),
                "expanded_canonical_ids": list(expanded),
                "context_budget": budget,
                "tokens_after_budget": sum(len(c["text"]) for c in final),
                "evidence_trace": [
                    {
                        "canonical_id": TARGET,
                        "chunk_fetched": fetched,
                        "reaches_final_context": any(
                            c["canonical_id"] == TARGET for c in final
                        ),
                        "drop_reason": None,
                    }
                ],
            }
        },
        "pre_budget_chunks": pool,
        "final_chunks": final,
    }


def test_target_lost_at_byte_allocation_when_earlier_documents_fill_the_budget():
    ahead = [chunk("docs/a.md#one", 2000), chunk("docs/b.md#two", 2000)]
    target = [chunk(TARGET, 500)]
    result = attribution.attribute(capture(ahead + target, ahead), TARGET)
    assert result["first_lost_stage"] == "byte_allocation"
    assert result["target_in_pool"] and not result["target_in_final"]
    assert result["documents_ahead_in_pool"] == 2
    assert result["final_slack_bytes"] == 96


def test_target_lost_before_the_pool_is_classified_as_chunk_limits():
    pool = [chunk("docs/a.md#one", 100)]
    result = attribution.attribute(capture(pool, pool, fetched=True), TARGET)
    assert result["first_lost_stage"] == "chunk_limits"


def test_target_never_fetched_is_classified_as_fetch():
    pool = [chunk("docs/a.md#one", 100)]
    result = attribution.attribute(capture(pool, pool, fetched=False), TARGET)
    assert result["first_lost_stage"] == "fetch"


def test_undiscovered_target_is_classified_as_discovery():
    pool = [chunk("docs/a.md#one", 100)]
    result = attribution.attribute(capture(pool, pool, seeds=()), TARGET)
    assert result["first_lost_stage"] == "discovery"


def test_delivered_target_has_no_lost_stage():
    pool = [chunk(TARGET, 100)]
    result = attribution.attribute(capture(pool, pool), TARGET)
    assert result["first_lost_stage"] is None
    assert result["target_in_final"]
