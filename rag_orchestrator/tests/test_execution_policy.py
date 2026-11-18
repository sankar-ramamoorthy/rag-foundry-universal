"""Phase 6 #384: mocked HTTP/embedding and scripted model, real selection and policy."""

import ast
import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from src.core import execution_policy as policy
from src.core import service
from test_wp_r4_payload import Backend, patch_pipeline

pytestmark = pytest.mark.unit

REPO = "00000000-0000-4000-8000-000000000001"
GEN = "00000000-0000-4000-8000-000000000002"
OTHER = "00000000-0000-4000-8000-000000000003"
PATH = "mealie/routes/recipe/exports.py"
# Lines 36-39 of the handler at the commit pinned by the public H questions.
EXCERPT = """        with get_temporary_path(auto_unlink=False) as temp_path:
            recipe = self.mixins.get_one(slug)
            file = self.service.render_template(recipe, temp_path, template_name)
            return FileResponse(file, background=BackgroundTask(rmtree, temp_path))
"""


def request(**kwargs):
    fields = {
        "repo_id": REPO,
        "generation_id": GEN,
        "question": "trace exports",
        "family": "execution_trace",
        "maximum_strategy": "investigation",
    }
    return policy.Request.model_validate(fields | kwargs)


class Fixture(Backend):
    def __init__(self):
        super().__init__()
        self.return_repo = REPO
        self.generation = GEN
        self.status = True

    def __call__(self, req):
        path = req.url.path
        if path.endswith("/generation"):
            return httpx.Response(
                200,
                json={"generation_status": "ready", "ingestion_id": self.generation},
            )
        scope = {"repo_id": self.return_repo, "generation_id": GEN}
        if path.endswith("/orient"):
            return httpx.Response(200, json={**scope, "ingestion_id": GEN})
        if "/source/" in path:
            assert req.url.params["generation_id"] == GEN
            if path.endswith("/files"):
                return httpx.Response(
                    200, json={**scope, "files": [{
                        "path": "a/module.py", "document_id": "module",
                    }]}
                )
            name = req.url.params["path"]
            text = (
                EXCERPT
                if name == PATH
                else "class C:\n async def f(self):\n  def inner(): pass\n"
            )
            return httpx.Response(
                200,
                json={
                    **scope,
                    "path": name,
                    "canonical_id": name,
                    "document_id": "module",
                    "text": text,
                    "complete_file": self.status and name != PATH,
                    "start_line": 36 if name == PATH else 1,
                    "end_line": 39 if name == PATH else 3,
                    "next_start_line": None,
                    "total_lines": 3 if self.status and name != PATH else None,
                    "returned_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                },
            )
        return super().__call__(req)


def test_existing_selection_parity_and_no_generation(monkeypatch):
    backend = Fixture()
    patch_pipeline(monkeypatch, backend)
    req = request()
    evidence = asyncio.run(
        policy.dispatch(req, policy.Search(tool="search_evidence", query=req.question))
    )
    assert backend.payload is None
    baseline = asyncio.run(service.run_rag(req.question, repo_id=REPO))
    rows = [dict(row) for row in evidence["passages"]]
    texts = [row.pop("text") for row in rows]
    assert rows and rows == baseline.retrieval_plan["final_context_manifest"]
    assert backend.payload is not None
    assert backend.payload["context"] == "\n\n".join(
        f"[Source: {row['source_label']}]\n{text}" for row, text in zip(rows, texts)
    )


def test_inventory_and_scope(monkeypatch):
    backend = Fixture()
    patch_pipeline(monkeypatch, backend)
    req = request(
        family="python_inventory", path="module.py", maximum_strategy="deterministic"
    )
    result = asyncio.run(policy.run_execution_policy(req))
    assert [row["name"] for row in result["inventory"]] == ["C.f", "C.f.inner"]
    assert result["completion"] == "verified_complete"
    assert result["model_calls"] == 0 and not backend.fetches
    backend.status = False
    assert (
        asyncio.run(policy.run_execution_policy(req))["termination_reason"]
        == "partial_source"
    )
    backend.return_repo = OTHER
    rejected = asyncio.run(policy.run_execution_policy(req))
    assert (
        rejected["termination_reason"] == "scope_mismatch" and not rejected["evidence"]
    )


def test_h3_scripted_partial_investigation(monkeypatch):
    route_text = '@router.get("/{slug}/exports", response_class=FileResponse)'

    class H3Backend(Fixture):
        def __call__(self, req):
            if req.url.path == "/v1/vectors/search":
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "document_id": "handler",
                                "chunk_id": "route",
                                "score": 1.0,
                                "text": route_text,
                                "metadata": {"canonical_id": PATH, "chunk_index": 0},
                            }
                        ]
                    },
                )
            return super().__call__(req)

    backend = H3Backend()
    patch_pipeline(monkeypatch, backend)
    questions = (
        Path(__file__).resolve().parents[2] / "DOCS/evaluations/359-H/questions.json"
    )
    question = next(
        q["question"]
        for q in json.loads(questions.read_text())["questions"]
        if q["qid"] == "H-3"
    )
    claim = "FileResponse schedules temporary-directory cleanup."
    steps = iter(
        [
            {
                "gap": "inspect the handler body for cleanup",
                "action": {
                    "tool": "read_source",
                    "path": PATH,
                    "start_line": 36,
                    "end_line": 39,
                },
            },
            {
                "findings": {claim: 1},
                "unresolved": ["JSON versus ZIP selection inside render_template"],
            },
        ]
    )

    async def mock_model(prompt, allowance):
        step = next(steps)
        assert (
            PATH
            in json.loads(prompt)["evidence"][0]["data"]["passages"][0]["canonical_id"]
        )
        if "findings" in step:
            assert "background=BackgroundTask(rmtree, temp_path)" in prompt
        return json.dumps(step)

    result = asyncio.run(
        policy.run_execution_policy(request(question=question), mock_model)
    )
    assert result["findings"] == {claim: 1} and result["completion"] == "incomplete"
    assert result["tool_calls"] == result["model_calls"] == 2
    assert result["evidence"][1]["data"]["path"] == PATH
    assert backend.payload is None


@pytest.mark.parametrize(
    "limits, reason",
    [
        ({"tool_calls": 0}, "tool_call_exhaustion"),
        ({"model_calls": 0}, "model_call_exhaustion"),
        ({"model_bytes": 1}, "model_byte_exhaustion"),
    ],
)
def test_budget(monkeypatch, limits, reason):
    patch_pipeline(monkeypatch, Fixture())

    async def forbidden(*args):
        pytest.fail("exhausted budget dispatched a model call")

    result = asyncio.run(policy.run_execution_policy(request(**limits), forbidden))
    assert (
        result["termination_reason"] == reason
        and result["completion"] == "budget_limited"
    )


def test_cross_action_generation_change(monkeypatch):
    backend = Fixture()
    patch_pipeline(monkeypatch, backend)

    async def switched(*args):
        backend.generation = OTHER
        return '{"gap":"inspect services","action":{"tool":"orient"}}'

    result = asyncio.run(policy.run_execution_policy(request(), switched))
    assert result["termination_reason"] == "stale_generation" and not result["evidence"]


def test_reject_model_scope_override(monkeypatch):
    patch_pipeline(monkeypatch, Fixture())

    async def override(*args):
        return json.dumps(
            {"gap": "inspect", "action": {"tool": "orient", "repo_id": OTHER}}
        )

    result = asyncio.run(policy.run_execution_policy(request(), override))
    assert (
        result["termination_reason"] == "invalid_action" and result["tool_calls"] == 1
    )


def test_orient_and_duplicate_dispatch(monkeypatch):
    backend = Fixture()
    patch_pipeline(monkeypatch, backend)

    async def repeated(*args):
        return '{"gap":"inspect repository structure","action":{"tool":"orient"}}'

    result = asyncio.run(policy.run_execution_policy(request(), repeated))
    assert result["termination_reason"] == "duplicate_action"
    assert [r["tool"] for r in result["evidence"]] == ["search_evidence", "orient"]
    assert result["tool_calls"] == 2


def test_search_rejects_internally_consistent_wrong_generation(monkeypatch):
    backend = Fixture()
    patch_pipeline(monkeypatch, backend)
    prepare = service.prepare_rag_evidence

    async def rebuild(*args, **kwargs):
        backend.generation = OTHER
        return await prepare(*args, **kwargs)

    monkeypatch.setattr(service, "prepare_rag_evidence", rebuild)
    result = asyncio.run(policy.run_execution_policy(request()))
    assert result["termination_reason"] == "stale_generation"
    assert not result["evidence"] and backend.payload is None


def test_foundry_module_inventory(monkeypatch):
    module = Path("rag_orchestrator/src/retrieval/codebase_utils.py")
    root = Path(__file__).resolve().parents[2]
    text = (root / module).read_text(encoding="utf-8")

    class ModuleFixture(Fixture):
        def __call__(self, req):
            if req.url.path.endswith("/read"):
                assert req.url.params["path"] == module.as_posix()
                return httpx.Response(
                    200,
                    json={
                        "repo_id": REPO,
                        "generation_id": GEN,
                        "path": module.as_posix(),
                        "canonical_id": module.as_posix(),
                        "document_id": "module",
                        "start_line": 1,
                        "end_line": len(text.splitlines()),
                        "next_start_line": None,
                        "total_lines": len(text.splitlines()),
                        "complete_file": True,
                        "text": text,
                        "returned_text_sha256": hashlib.sha256(
                            text.encode()
                        ).hexdigest(),
                    },
                )
            return super().__call__(req)

    backend = ModuleFixture()
    patch_pipeline(monkeypatch, backend)
    result = asyncio.run(
        policy.run_execution_policy(
            request(
                family="python_inventory",
                path=module.as_posix(),
                maximum_strategy="deterministic",
            )
        )
    )
    names = {row["name"] for row in result["inventory"]}
    assert len(names) == 13 and "get_cached_graph_with_generation" in names
    assert result["completion"] == "verified_complete" and result["tool_calls"] == 1
    assert result["model_calls"] == 0 and not backend.fetches


class PagedModule(Fixture):
    def __init__(self, source, final_changes=None, page_cap=500):
        super().__init__()
        self.lines = source.splitlines(keepends=True)
        self.starts = []
        self.page_cap = page_cap
        self.final_changes = final_changes or {}

    def __call__(self, req):
        if not req.url.path.endswith("/read"):
            return super().__call__(req)
        params = req.url.params
        start = int(params.get("start_line", 0))
        self.starts.append(start)
        if not self.lines and start:
            return httpx.Response(416, json={"error_code": "INVALID_LINE_RANGE"})
        if not start:
            assert not self.lines  # Whole-file requests only confirm empty source.
        end = min(int(params.get("end_line", 0)), len(self.lines))
        if end - start + 1 > self.page_cap:
            return httpx.Response(413, json={"error_code": "READ_TOO_LARGE"})
        text = "".join(self.lines[max(0, start - 1) : end])
        eof = end == len(self.lines)
        data = {
            "repo_id": REPO,
            "generation_id": GEN,
            "canonical_id": params["path"],
            "path": params["path"],
            "document_id": "module",
            "start_line": start,
            "end_line": end,
            "next_start_line": None if eof else end + 1,
            "total_lines": end if eof else None,
            "complete_file": start <= 1 and eof,
            "text": text,
            "returned_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        }
        if eof:
            data.update(self.final_changes)
        return httpx.Response(200, json=data)


def test_large_inventory_public_route_matches_full_ast(monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.v1.main import app

    path = "ingestion_service/src/api/v1/codebase_ingest.py"
    source = (Path(__file__).resolve().parents[2] / path).read_text(encoding="utf8")
    backend = PagedModule(source)
    patch_pipeline(monkeypatch, backend)
    data = (
        TestClient(app)
        .post(
            "/v1/rag",
            json={
                "repo_id": REPO,
                "query": f"What functions are in {path}?",
            },
        )
        .json()
    )
    tree = ast.parse(source)
    parents = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }
    expected = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = [node.name]
            ancestor = node
            while ancestor in parents:
                ancestor = parents[ancestor]
                if isinstance(
                    ancestor, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    names.append(ancestor.name)
            expected.append(
                {
                    "name": ".".join(reversed(names)),
                    "start": node.lineno,
                    "end": node.end_lineno,
                    "kind": "async"
                    if isinstance(node, ast.AsyncFunctionDef)
                    else "sync",
                }
            )
    plan = data["retrieval_plan"]
    assert backend.starts == [1, 501] and data["sources"] == [path]
    assert plan["inventory"] == sorted(expected, key=lambda row: row["start"])
    assert plan["returned_text_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert plan["completion"] == "verified_complete"
    assert plan["model_calls"] == 0 and backend.payload is None


@pytest.mark.parametrize(
    ("changes", "budget", "reason"),
    [
        ({}, 1, "tool_call_exhaustion"),
        ({"generation_id": OTHER}, 2, "stale_generation"),
        ({"document_id": OTHER}, 2, "invalid_source"),
        ({"canonical_id": "other.py"}, 2, "invalid_source"),
        ({"start_line": 500}, 2, "partial_source"),
        ({"total_lines": None}, 2, "partial_source"),
        ({"next_start_line": 501}, 2, "partial_source"),
        ({"returned_text_sha256": ""}, 2, "invalid_source"),
    ],
)
def test_interrupted_parseable_inventory(monkeypatch, changes, budget, reason):
    prefix = "def first(): pass\r\n" + "# café\r\n" * 499
    ast.parse(prefix)
    backend = PagedModule(prefix + "def last(): pass", changes)
    patch_pipeline(monkeypatch, backend)
    req = request(family="python_inventory", path="a/module.py", tool_calls=budget)
    result = asyncio.run(policy.run_execution_policy(req))
    assert result["termination_reason"] == reason
    assert result["completion"] == ("budget_limited" if budget == 1 else "incomplete")
    assert "inventory" not in result and result["model_calls"] == 0
    assert len(backend.starts) == budget


@pytest.mark.parametrize(
    ("source", "cap", "starts", "names"),
    [
        ("", 500, [1, 0], []),
        (
            "# café\r\n" * 499 + "class C:\r\n async def f(self): pass",
            250,
            [1, 1, 251, 501],
            ["C.f"],
        ),
    ],
)
def test_empty_and_size_limited_pages(monkeypatch, source, cap, starts, names):
    backend = PagedModule(source, page_cap=cap)
    patch_pipeline(monkeypatch, backend)
    req = request(family="python_inventory", path="module.py")
    result = asyncio.run(policy.run_execution_policy(req))
    assert result["completion"] == "verified_complete"
    assert result["returned_text_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert [row["name"] for row in result["inventory"]] == names
    assert backend.starts == starts and result["tool_calls"] == 1 + len(starts)


@pytest.mark.parametrize(
    "question",
    [
        "What functions are defined in module.py?",
        "what functions does module.py have",
        "Which functions does `a/module.py` define?",
    ],
)
def test_inventory_through_public_route(monkeypatch, question):
    from fastapi.testclient import TestClient
    from src.api.v1.main import app

    backend = Fixture()
    patch_pipeline(monkeypatch, backend)
    response = TestClient(app).post(
        "/v1/rag",
        json={
            "repo_id": REPO,
            "query": question,
            "context_mode": "custom",
            "max_evidence_bytes": 8192,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "C.f.inner" in data["answer"]
    assert data["sources"] == ["a/module.py"]
    assert data["retrieval_plan"]["model_calls"] == 0 and backend.payload is None
    assert "text" not in data["retrieval_plan"]


def test_inventory_does_not_capture_explanations_or_standard_rag():
    from src.api.v1.models import RAGQuery
    from src.core.inventory_query import inventory_response

    for query, mode in [
        ("What functions are defined in module.py?", "rag"),
        ("What functions are defined in module.py and how do they interact?", "auto"),
        ("How does module.py work?", "auto"),
        ("What functions does module.py have and how do they interact?", "auto"),
        ("What functions does module.py have?", "rag"),
    ]:
        req = RAGQuery.model_validate({"query": query, "execution_mode": mode})
        assert asyncio.run(inventory_response(req)) is None


def test_inventory_ambiguity_returns_paths_without_reading(monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.v1.main import app

    class Ambiguous(Fixture):
        def __call__(self, req):
            if req.url.path.endswith("/files"):
                return httpx.Response(200, json={
                    "repo_id": REPO, "generation_id": GEN,
                    "files": [{"path": "a/mod.py"}, {"path": "b/mod.py"}],
                })
            assert not req.url.path.endswith("/read")
            return super().__call__(req)

    patch_pipeline(monkeypatch, Ambiguous())
    data = TestClient(app).post("/v1/rag", json={
        "repo_id": REPO, "query": "List all functions in mod.py",
    }).json()
    assert "a/mod.py" in data["answer"] and "b/mod.py" in data["answer"]
    assert data["retrieval_plan"]["termination_reason"] == "clarification"


def test_missing_inventory_file_through_public_route(monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.v1.main import app

    class Missing(Fixture):
        def __call__(self, req):
            if req.url.path.endswith("/files"):
                return httpx.Response(200, json={
                    "repo_id": REPO, "generation_id": GEN, "files": [],
                })
            assert not req.url.path.endswith("/read")
            return super().__call__(req)

    backend = Missing()
    patch_pipeline(monkeypatch, backend)
    response = TestClient(app).post("/v1/rag", json={
        "repo_id": REPO, "query": "what functions are in ingrst.py",
    })
    assert response.status_code == 200
    result = response.json()
    assert "ingrst.py" in result["answer"] and "spelling" in result["answer"]
    assert result["retrieval_plan"]["termination_reason"] == "file_not_found"
    assert result["retrieval_plan"]["model_calls"] == 0 and backend.payload is None
