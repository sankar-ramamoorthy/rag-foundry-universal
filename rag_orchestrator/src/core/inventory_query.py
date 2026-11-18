"""Recognize explicit single-file inventory requests at the repository API boundary."""

import re

from src.api.v1.models import RAGQuery, RAGResponse
from src.core import execution_policy, service

_INVENTORY = re.compile(
    r"(?:please\s+)?(?:(?:what|which)\s+(?:python\s+)?functions\s+"
    r"(?:are\s+)?(?:defined\s+)?in|(?:list|show|enumerate)\s+"
    r"(?:(?:all|the)\s+)*(?:python\s+)?functions\s+(?:defined\s+)?in)"
    r"\s+(?:the\s+file\s+)?(?P<quote>[\x22'`]?)(?P<path>(?:[\w.-]+/)*[\w.-]+\.py)"
    r"(?P=quote)[?.!]?",
    re.IGNORECASE,
)


async def inventory_response(query: RAGQuery) -> RAGResponse | None:
    if (
        query.execution_mode == "rag"
        or query.claim_type
        or query.language
        not in (
            None,
            "python",
        )
    ):
        return None
    match = _INVENTORY.fullmatch(query.query.strip())
    if not match:
        return None
    name = match["path"]
    repo = await service.resolve_repo_id_http(query.repo_id)
    generation = await service._query_generation(repo)
    result = await execution_policy.run_execution_policy(
        execution_policy.Request.model_validate(
            {
                "repo_id": repo,
                "generation_id": generation,
                "question": query.query,
                "path": name,
                "family": "python_inventory",
                "maximum_strategy": "deterministic",
            }
        )
    )
    plan = {
        key: result[key]
        for key in (
            "generation_id",
            "completion",
            "termination_reason",
            "tool_calls",
            "model_calls",
        )
    }
    plan["strategy"] = "python_inventory"
    sources = []
    if result["completion"] == "verified_complete":
        source = result["evidence"][-1]["data"]
        path = source["path"]
        sources.append(path)
        plan["returned_text_sha256"] = source["returned_text_sha256"]
        rows = result["inventory"]
        plan["inventory"] = rows
        lines = [f"{len(rows)} Python functions defined in {path}:"]
        lines.extend(f"- {r['name']} (lines {r['start']}-{r['end']})" for r in rows)
        answer = "\n".join(lines)
    elif result["termination_reason"] == "clarification":
        files = result["evidence"][0]["data"]["files"]
        answer = "Please specify the repository-relative path. Matching files:\n"
        answer += "\n".join(f"- {f['path']}" for f in files)
    else:
        answer = f"Could not inventory {name} ({result['termination_reason']})."
    return RAGResponse(
        answer=answer,
        sources=sources,
        repo_id=repo,
        retrieval_plan=plan,
        trace_id=service._new_trace_id(),
    )
