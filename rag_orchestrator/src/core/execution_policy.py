"""Opt-in Phase 6 execution policy (#384). Python harness entry point."""

import ast
import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal, Union
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from src.core import evidence_service, service


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Request(Contract):
    repo_id: UUID
    generation_id: UUID
    question: str = Field(min_length=1, max_length=8192)
    family: Literal["python_inventory", "execution_trace"]
    path: str | None = Field(default=None, max_length=1024)
    maximum_strategy: Literal["deterministic", "retrieval", "investigation"]
    tool_calls: int = Field(default=8, ge=0, le=40)
    model_calls: int = Field(default=10, ge=0, le=42)
    wall_seconds: float = Field(default=60, gt=0, le=600)
    # Conservative input + output byte allowance for the injected JSON proposer.
    model_bytes: int = Field(default=32000, ge=0, le=1000000)


class Orient(Contract):
    tool: Literal["orient"]


class Find(Contract):
    tool: Literal["find_source"]
    pattern: str = Field(min_length=1, max_length=1024)
    cursor: str | None = Field(default=None, max_length=4096)


class Read(Contract):
    tool: Literal["read_source"]
    path: str = Field(min_length=1, max_length=1024)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class Search(Contract):
    tool: Literal["search_evidence"]
    query: str = Field(min_length=1, max_length=8192)


Action = Annotated[Union[Orient, Find, Read, Search], Field(discriminator="tool")]


class Repair(Contract):
    gap: str = Field(min_length=1, max_length=1024)
    action: Action


class Finish(Contract):
    # Evidence IDs refer only to records admitted to this investigation.
    findings: dict[str, int]
    unresolved: list[str]


proposal = TypeAdapter(Union[Repair, Finish])
Propose = Callable[[str, int], Awaitable[str]]


class Stop(Exception):
    pass


async def dispatch(request: Request, action: Action):
    repo, generation = str(request.repo_id), str(request.generation_id)
    await service._verify_generation(repo, generation)
    if isinstance(action, Search):
        assembled, plan, *_ = await service.prepare_rag_evidence(
            action.query, repo, service._new_trace_id()
        )
        result = {
            "repo_id": repo,
            "generation_id": plan["generation_id"],
            "trace_id": plan["trace_id"],
            "passages": [
                {**row, "text": chunk["text"]}
                for row, chunk in zip(
                    plan["final_context_manifest"], assembled.chunks, strict=True
                )
            ],
        }
    elif isinstance(action, Orient):
        result = await evidence_service.fetch_orient_response(repo)
        result = {**result, "generation_id": result.get("ingestion_id")}
    else:
        path = "files" if isinstance(action, Find) else "read"
        params = action.model_dump(exclude={"tool"}, exclude_none=True)
        if (
            isinstance(action, Read)
            and action.end_line is not None
            and (
                action.start_line is None
                or not 0 <= action.end_line - action.start_line < 500
            )
        ):
            raise Stop("invalid_action")
        params["generation_id"] = generation
        base = service.get_settings().INGESTION_SERVICE_URL
        url = f"{base}/v1/repos/{repo}/source/{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params)
        if response.is_error:
            code = response.json().get("error_code", "service_failure")
            raise Stop("stale_generation" if code == "GENERATION_MISMATCH" else code)
        result = response.json()
    if result.get("repo_id") != repo:
        raise Stop("scope_mismatch")
    if result.get("generation_id") != generation:
        raise Stop("stale_generation")
    if isinstance(action, Read):
        digest = hashlib.sha256(result["text"].encode()).hexdigest()
        if result["path"] != action.path or digest != result["returned_text_sha256"]:
            raise Stop("invalid_source")
    await service._verify_generation(repo, generation)
    return result


def inventory(text: str):
    rows = []

    def visit(node, parents):
        for child in ast.iter_child_nodes(node):
            scope = parents
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                scope = (*parents, child.name)
                if not isinstance(child, ast.ClassDef):
                    rows.append(
                        {
                            "name": ".".join(scope),
                            "start": child.lineno,
                            "end": child.end_lineno,
                            "kind": "async"
                            if isinstance(child, ast.AsyncFunctionDef)
                            else "sync",
                        }
                    )
            visit(child, scope)

    visit(ast.parse(text), ())
    return rows


class Investigation:
    def __init__(self, request: Request, propose: Propose | None):
        self.request = request
        self.propose = propose
        self.ledger = []
        self.decisions = []
        self.visited = set()
        self.result = {
            "repo_id": str(request.repo_id),
            "generation_id": str(request.generation_id),
            "evidence": self.ledger,
            "decisions": self.decisions,
            "findings": {},
            "unresolved": [request.question],
            "completion": "incomplete",
            "tool_calls": 0,
            "model_calls": 0,
            "model_bytes": 0,
        }

    async def execute(self, action, reason):
        key = action.model_dump_json()
        self.decisions.append(
            {"action": action.model_dump(exclude_none=True), "reason": reason}
        )
        if key in self.visited:
            raise Stop("duplicate_action")
        if self.result["tool_calls"] >= self.request.tool_calls:
            raise Stop("tool_call_exhaustion")
        self.visited.add(key)
        self.result["tool_calls"] += 1
        data = await dispatch(self.request, action)
        self.ledger.append({"id": len(self.ledger), "tool": action.tool, "data": data})
        return data

    async def list_functions(self):
        if not self.request.path:
            raise Stop("clarification")
        path = self.request.path
        if "/" not in path:
            found = await self.execute(
                Find(tool="find_source", pattern="**/" + path),
                "resolve the supplied basename",
            )
            if len(found["files"]) != 1 or found.get("next_cursor"):
                raise Stop("clarification" if found["files"] else "file_not_found")
            path = found["files"][0]["path"]
        source = await self.execute(
            Read(tool="read_source", path=path), "inspect complete module"
        )
        if not source["complete_file"]:
            raise Stop("partial_source")
        self.result["inventory"] = inventory(source["text"])
        self.result.update(unresolved=[], completion="verified_complete")

    async def next_step(self):
        if self.result["model_calls"] >= self.request.model_calls:
            raise Stop("model_call_exhaustion")
        prompt = json.dumps(
            {
                "question": self.request.question,
                "evidence": self.ledger,
                "response_schema": proposal.json_schema(),
            },
            ensure_ascii=False,
        )
        size = len(prompt.encode())
        remaining = self.request.model_bytes - self.result["model_bytes"] - size
        if remaining <= 0:
            raise Stop("model_byte_exhaustion")
        self.result["model_calls"] += 1
        self.result["model_bytes"] += size
        assert self.propose is not None
        raw = await self.propose(prompt, remaining)
        output_size = len(raw.encode())
        self.result["model_bytes"] += output_size
        if output_size > remaining:
            raise Stop("model_byte_exhaustion")
        return proposal.validate_json(raw, strict=True)

    async def finish(self, step: Finish):
        if any(idx < 0 or idx >= len(self.ledger) for idx in step.findings.values()):
            raise Stop("invalid_citation")
        await service._verify_generation(
            str(self.request.repo_id), str(self.request.generation_id)
        )
        if not step.findings and not step.unresolved:
            raise Stop("invalid_assessment")
        self.result.update(findings=step.findings, unresolved=step.unresolved)
        if step.findings and not step.unresolved:
            self.result["completion"] = "evidence_supported"

    async def run(self):
        if self.request.family == "python_inventory":
            await self.list_functions()
            return
        if self.request.maximum_strategy == "deterministic":
            raise Stop("strategy_limit")
        await self.execute(
            Search(tool="search_evidence", query=self.request.question),
            "discover evidence for the requested execution trace",
        )
        if self.request.maximum_strategy != "investigation":
            raise Stop("strategy_limit")
        if self.propose is None:
            raise Stop("model_unavailable")
        while True:
            step = await self.next_step()
            if isinstance(step, Finish):
                await self.finish(step)
                return
            await self.execute(step.action, step.gap)


async def run_execution_policy(request: Request, propose: Propose | None = None):
    """Execute one request. Model proposals use an injected bounded JSON transport."""
    investigation = Investigation(request, propose)
    result = investigation.result
    try:
        await asyncio.wait_for(investigation.run(), request.wall_seconds)
        reason = "completed" if not result["unresolved"] else "no_useful_repair"
    except Stop as exc:
        reason = str(exc)
    except asyncio.CancelledError:
        reason = "cancellation"
    except asyncio.TimeoutError:
        reason = "timeout"
    except ValidationError:
        reason = "invalid_action"
    except HTTPException as exc:
        reason = "stale_generation" if exc.status_code == 409 else "service_failure"
    except (httpx.HTTPError, ValueError, KeyError, SyntaxError, RecursionError):
        reason = (
            "invalid_source"
            if request.family == "python_inventory"
            else "service_failure"
        )
    if reason in {"scope_mismatch", "stale_generation"}:
        investigation.ledger.clear()
    if reason.endswith("_exhaustion") or reason == "timeout":
        result["completion"] = "budget_limited"
    return {**result, "termination_reason": reason}
