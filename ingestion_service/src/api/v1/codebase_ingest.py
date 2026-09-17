from uuid import uuid4, UUID
import logging
from pathlib import Path
import tempfile
import shutil
from collections.abc import Callable
from functools import partial

from fastapi import APIRouter, HTTPException, Form, status
from pydantic import BaseModel

from src.core.database_session import get_sessionmaker
from src.core.models import IngestionRequest
from src.core.status_manager import StatusManager
from src.core.ingestion_jobs import submit_ingestion
from src.core.ingestion_ownership import AdmissionBusy, RepositoryBusy
from src.core.codebase.repo_graph_builder import RepoGraphBuilder
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence
from src.core.pipeline import IngestionPipeline

from src.core.config import get_settings
from shared.embedders.factory import get_embedder
from src.core.http_vectorstore import HttpVectorStore
from src.core.codebase.identity import build_repo_id
from src.core.repo_naming import derive_repo_identity
from src.core.codebase.embedding_buffer import EmbeddingBuffer
from src.core.codebase.language import language_for_path
from src.core.config import Settings
# -----------------------------
# Session and router
# -----------------------------
SessionLocal = get_sessionmaker()
router = APIRouter(tags=["codebase_ingest"])
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# -----------------------------
# Temporary pipeline builder (TECH DEBT - see issue)
# -----------------------------
class NoOpValidator:
    def validate(self, text: str) -> None:
        return None


def _build_pipeline(provider: str) -> IngestionPipeline:
    settings = get_settings()

    embedder = get_embedder(
        provider=settings.EMBEDDING_PROVIDER,
        ollama_base_url=settings.OLLAMA_BASE_URL,
        ollama_model=settings.OLLAMA_EMBED_MODEL,
        ollama_batch_size=settings.OLLAMA_BATCH_SIZE,
        ollama_dimension=settings.VECTOR_DIMENSION,
    )

    vector_store = HttpVectorStore(
        base_url=settings.VECTOR_STORE_SERVICE_URL,
        provider=provider,
    )

    return IngestionPipeline(
        validator=NoOpValidator(),
        embedder=embedder,
        vector_store=vector_store,
    )


# -----------------------------
# Request / Response Models
# -----------------------------
class RepoIngestRequest(BaseModel):
    git_url: str | None = None
    local_path: str | None = None
    provider: str | None = None  # Embedding provider


class RepoIngestResponse(BaseModel):
    ingestion_id: UUID
    status: str
    embed_progress: dict | None = None


# -----------------------------
# Batch embedding stage (F-08 / WP-S2)
# -----------------------------
def _embed_repo_artifacts(
    pipeline: IngestionPipeline,
    persistence: CodebaseGraphPersistence,
    repo_id: str,
    ingestion_id: str,
    expected_nodes: int,
    provider: str,
    settings: Settings,
    report_progress: Callable[[dict], None],
) -> tuple[int, int]:
    """Page persisted artifacts; bound chunk and vector state independently.

    Missing/replaced nodes fail the attempt instead of silently losing evidence.
    Return shape retains the legacy skipped counter, now necessarily zero.
    """
    progress: dict = {
        "stage": "embedding", "nodes_processed": 0, "nodes_total": 0,
        "chunks_persisted": 0, "max_buffer_chunks": 0, "max_buffer_bytes": 0,
    }
    report_progress(dict(progress))  # BEFORE preflight/count/page allocation.

    def pages():
        return persistence.iter_artifact_pages(
            repo_id, ingestion_id, page_size=settings.INGESTION_NODE_PAGE_SIZE,
            max_artifact_bytes=settings.INGESTION_MAX_ARTIFACT_BYTES,
            expected_nodes=expected_nodes,
        )

    # A bounded scan preserves Python's exact Unicode strip semantics.
    for page in pages():
        progress["nodes_total"] += sum(bool((row.text or "").strip()) for row in page)
        del page
    report_progress(dict(progress))

    def acknowledged():
        progress.update(
            chunks_persisted=buffer.chunks_persisted,
            max_buffer_chunks=buffer.max_buffer_chunks,
            max_buffer_bytes=buffer.max_buffer_bytes,
        )
        report_progress(dict(progress))

    buffer = EmbeddingBuffer(
        pipeline, ingestion_id, max_chunks=settings.INGESTION_EMBED_BATCH_SIZE,
        max_bytes=settings.INGESTION_EMBED_MAX_BYTES, on_flush=acknowledged,
    )

    def append_page(page):
        # Frame exit drops the last artifact's text/chunk-list references.
        for node in page:
            if not (node.text or "").strip():
                continue
            chunks = pipeline._chunk(node.text, "code", provider)
            for ordinal, chunk in enumerate(chunks):
                chunk.metadata.update(
                    canonical_id=node.canonical_id, repo_id=repo_id,
                    relative_path=node.relative_path, doc_type=node.doc_type,
                    language=language_for_path(node.relative_path),
                    source_metadata={
                        **chunk.metadata.get("source_metadata", {}),
                        "canonical_id": node.canonical_id,
                    },
                )
                buffer.append(chunk, str(node.document_id), ordinal)
            progress["nodes_processed"] += 1
            del chunks

    for page in pages():
        append_page(page)
        del page  # Do not retain predecessor page during generator advancement.
        acknowledged()
    if progress["nodes_processed"] != progress["nodes_total"]:
        raise RuntimeError("Embeddable artifact count changed during embedding")
    buffer.flush()
    acknowledged()
    return buffer.chunks_persisted, 0


def _build_and_persist_graph(
    repo_path, repo_id, ingestion_id, persistence, report_stage,
):
    """Own all graph/IR references in a frame that ends before embedding."""
    report_stage("graph_build")
    builder = RepoGraphBuilder(
        repo_root=Path(repo_path), ingestion_id=str(ingestion_id),
    )
    graph = builder.build()
    report_stage("graph_persist")
    return persistence.persist_graph(
        repo_id=repo_id, nodes=graph.all_entities(), relationships=graph.relationships,
    )


# -----------------------------
# Background ingestion worker
# -----------------------------
def _background_ingest_repo(
    ingestion_id: UUID,
    git_url: str | None,
    local_path: str | None,
    provider: str | None,
):
    """
    Clone or use local repo, build graph, persist nodes &
    relationships, and embed code artifacts.
    """
    session = SessionLocal()

    temp_dir = None
    try:
        StatusManager(session).mark_running(ingestion_id)
        logger.debug(f"[{ingestion_id}] Starting background ingestion")
        logger.debug(
            f"[{ingestion_id}] git_url={git_url}, "
            f"local_path={local_path}, provider={provider}"
        )

        if git_url:
            import git  # GitPython
            temp_dir = tempfile.mkdtemp()
            logger.debug(f"Cloning {git_url} into {temp_dir}")
            git.Repo.clone_from(git_url, temp_dir)
            repo_path = temp_dir
            repo_id_url = git_url
        elif local_path:
            repo_path = str(Path(local_path).resolve())
            logger.info(f"[{ingestion_id}] Using local repo path: {repo_path}")
            repo_id_url = repo_path
        else:
            raise ValueError("Either git_url or local_path must be provided")
        logger.debug(
            f"build_repo_id({repo_id_url}) calculates "
            f"repo_id = {build_repo_id(repo_id_url)}"
        )
        repo_id = build_repo_id(repo_id_url)

        persistence = CodebaseGraphPersistence(session=session)
        report_progress = partial(
            StatusManager(session).update_embed_progress, ingestion_id,
        )
        stats = _build_and_persist_graph(
            repo_path, repo_id, ingestion_id, persistence,
            lambda stage: report_progress({
                "stage": stage, "nodes_processed": 0, "nodes_total": 0,
                "chunks_persisted": 0, "max_buffer_chunks": 0, "max_buffer_bytes": 0,
            }),
        )
        logger.info(f"[{ingestion_id}] Graph persisted: {stats}")

        # --- Run embeddings via IngestionPipeline ---
        settings = get_settings()
        provider = settings.EMBEDDING_PROVIDER
        pipeline = _build_pipeline(provider)

        # #160: graph frame has ended; only bounded persisted pages feed embedding.
        chunk_count, skipped_missing = _embed_repo_artifacts(
            pipeline=pipeline,
            persistence=persistence,
            repo_id=repo_id,
            ingestion_id=str(ingestion_id),
            expected_nodes=stats["nodes"],
            provider=provider,
            settings=settings,
            report_progress=report_progress,
        )
        logger.info(
            f"[{ingestion_id}] Embedded {chunk_count} chunks "
            f"({skipped_missing} nodes had no DB record)"
        )

        StatusManager(session).mark_completed(ingestion_id)
        logger.info(f"✅ Repo ingestion completed: {ingestion_id}")

        # #166: this generation's graph+vectors are both confirmed complete;
        # any older ingestion_id for the same repo_id is now dead weight --
        # its document_nodes were already atomically replaced by
        # persist_graph, but its vectors survive until explicitly removed.
        # Best-effort and non-fatal: a failure here leaves stale vectors
        # (degraded recall, not incorrect data for the new generation) and
        # is not grounds to mark an otherwise-complete ingestion failed.
        try:
            from src.core import db_utils

            stale_ids = db_utils.superseded_ingestion_ids_for_repo(
                repo_id, str(ingestion_id),
            )
            settings = get_settings()
            vector_store = HttpVectorStore(
                base_url=settings.VECTOR_STORE_SERVICE_URL,
            )
            for stale_id in stale_ids:
                vector_store.delete_by_ingestion_id(stale_id)
            db_utils.delete_ingestion_requests(stale_ids)
            if stale_ids:
                logger.info(
                    f"[{ingestion_id}] Cleaned up {len(stale_ids)} superseded "
                    f"generation(s) for repo {repo_id[:8]}"
                )
        except Exception:
            logger.exception(
                f"[{ingestion_id}] Superseded-generation cleanup failed for "
                f"repo {repo_id[:8]}; stale vectors may remain (retry later "
                "via DELETE /v1/repos/{repo_id} sweeping all historical ids)"
            )

    except Exception as exc:
        logger.exception(f"❌ Repo ingestion failed: {ingestion_id}")
        session.rollback()
        StatusManager(session).mark_failed(ingestion_id, error=str(exc))

    finally:
        if temp_dir:
            shutil.rmtree(temp_dir)
        session.close()


# -----------------------------
# POST /v1/codebase/ingest-repo
# -----------------------------
@router.post(
    "/ingest-repo",
    response_model=RepoIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_repo(
    git_url: str | None = Form(default=None),
    local_path: str | None = Form(default=None),
    provider: str | None = Form(default=None),
) -> RepoIngestResponse:
    if not git_url and not local_path:
        raise HTTPException(
            status_code=400, detail="Must provide either git_url or local_path"
        )
    repo_id_url: str = git_url or local_path  # type: ignore[assignment]

    ingestion_id = uuid4()
    metadata = {"git_url": git_url, "local_path": local_path, "provider": provider}
    # Issue #30 Part 5: persist the derived display identity alongside the
    # raw source so it stays queryable; derivation lives in repo_naming.
    identity = derive_repo_identity(metadata)
    metadata.update(
        {k: identity[k] for k in ("source_type", "name", "display_name")}
    )
    # #166: repo_id is a pure function of the source URL/path, so it is
    # known and persisted at accept time — before any clone — independent
    # of document_nodes. This also lets delete_repo find/enumerate this
    # attempt even if the worker never writes a single graph row.
    repo_id = build_repo_id(repo_id_url)
    try:
        submit_ingestion(
            ingestion_id=ingestion_id, source_type="repo", metadata=metadata,
            target=_background_ingest_repo,
            prepare=lambda: {
            "git_url": git_url,
            "local_path": local_path,
            "provider": provider,
            },
            repo_id=repo_id,
        )
    except AdmissionBusy as exc:
        raise HTTPException(
            status_code=503, detail=str(exc), headers={"Retry-After": "5"},
        ) from exc
    except RepositoryBusy as exc:
        raise HTTPException(
            status_code=409, detail=str(exc), headers={"Retry-After": "5"},
        ) from exc

    return RepoIngestResponse(ingestion_id=ingestion_id, status="accepted")


# -----------------------------
# GET /v1/codebase/ingest-repo/{ingestion_id}
# -----------------------------
@router.get("/ingest-repo/{ingestion_id}", response_model=RepoIngestResponse)
def get_repo_ingest_status(ingestion_id: str) -> RepoIngestResponse:
    try:
        ingestion_uuid = UUID(ingestion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ingestion ID format")

    with SessionLocal() as session:
        request = (
            session.query(IngestionRequest)
            .filter_by(ingestion_id=ingestion_uuid)
            .first()
        )
        if not request:
            raise HTTPException(status_code=404, detail="Ingestion ID not found")

        return RepoIngestResponse(
            ingestion_id=request.ingestion_id, status=request.status,
            embed_progress=(request.ingestion_metadata or {}).get("embed_progress"),
        )
