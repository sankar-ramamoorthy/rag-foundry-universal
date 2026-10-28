"""Read-only #240 evaluation adapter for a production generation.

All ordinary ingestion reads are forwarded to a pinned production corpus.
Only the new Compose route uses the real ingestion route implementation with
an in-memory summary built from a clean checkout of that corpus's source SHA.
This tests answer quality before a new ingestion runtime is deployed; it is
not a production verification of snapshot persistence.
"""

import os
import subprocess
import sys
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ingestion_service"))

from src.api.v1 import repos  # noqa: E402
from src.core.codebase.structural_inventory import build_structural_inventory  # noqa: E402

SOURCE = Path(os.environ["ISSUE240_SOURCE_PATH"]).resolve()
REPO_ID = os.environ["ISSUE240_REPO_ID"]
GENERATION_ID = os.environ["ISSUE240_GENERATION_ID"]
SOURCE_SHA = os.environ["ISSUE240_SOURCE_SHA"]
REMOTE = os.environ["ISSUE240_REMOTE_INGESTION"]


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={SOURCE}", "-C", str(SOURCE), *args],
        text=True,
        timeout=30,
    ).strip()


if _git("rev-parse", "HEAD") != SOURCE_SHA or _git("status", "--porcelain"):
    raise RuntimeError("Evaluation source must be a clean pinned checkout")

SUMMARY = build_structural_inventory(SOURCE).summary_dict()
if not SUMMARY["compose_documents"]:
    raise RuntimeError("Pinned source has no parsed Compose content")

repos.db_utils.resolve_current_generation = (  # type: ignore[assignment]
    lambda repo_id: GENERATION_ID if repo_id == REPO_ID else None
)
repos.db_utils.generation_status = lambda _: "ready"  # type: ignore[assignment]
repos.db_utils.get_structural_summary = lambda _: SUMMARY  # type: ignore[assignment]
repos.db_utils.generation_lineage = (  # type: ignore[assignment]
    lambda _: {"commit_sha": SOURCE_SHA}
)

app = FastAPI()
app.add_api_route(
    "/v1/repos/{repo_id}/compose-snapshot",
    repos.get_repo_compose_snapshot,
    methods=["GET"],
)


async def _forward(request: Request) -> Response:
    path = request.url.path
    if request.method == "POST" and not path.endswith("/nodes/lookup"):
        raise HTTPException(405, "Evaluation proxy allows read-only requests")
    url = f"{REMOTE}{path}"
    async with httpx.AsyncClient(timeout=90) as client:
        remote = await client.request(
            request.method,
            url,
            params=request.query_params,
            content=await request.body(),
            headers={"content-type": request.headers.get("content-type", "")},
        )
    return Response(
        content=remote.content,
        status_code=remote.status_code,
        media_type=remote.headers.get("content-type"),
    )


app.add_api_route("/{path:path}", _forward, methods=["GET", "POST"])
