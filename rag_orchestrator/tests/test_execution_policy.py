"""Phase 6 #384: mocked HTTP/embedding and scripted model, real selection and policy."""

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
                    200, json={**scope, "files": [{"path": "a/module.py"}]}
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
                    "text": text,
                    "complete_file": self.status and name != PATH,
                    "start_line": 36 if name == PATH else 1,
                    "end_line": 39 if name == PATH else 3,
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
