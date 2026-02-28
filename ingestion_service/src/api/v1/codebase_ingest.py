import uuid
from uuid import uuid4, UUID, uuid5
import threading
import logging
from pathlib import Path
import tempfile
import shutil

from fastapi import APIRouter, HTTPException, Form, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.database_session import get_sessionmaker
from src.core.models import IngestionRequest
from src.core.status_manager import StatusManager
from src.core.codebase.repo_graph_builder import RepoGraphBuilder
from src.core.codebase.codebase_persistence import CodebaseGraphPersistence
from src.core.pipeline import IngestionPipeline

from src.core.config import get_settings
from shared.embedders.factory import get_embedder
from src.core.http_vectorstore import HttpVectorStore
from src.core.codebase.identity import build_repo_id
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
    Clone or use local repo, build graph, persist nodes & relationships, and embed code artifacts.
    """
    session = SessionLocal()
    StatusManager(session).mark_running(ingestion_id)

    temp_dir = None
    try:
        logger.debug(f"[{ingestion_id}] Starting background ingestion")
        logger.debug(f"[{ingestion_id}] git_url={git_url}, local_path={local_path}, provider={provider}")

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
        logger.debug(f"build_repo_id({repo_id_url}) calculates repo_id = {build_repo_id(repo_id_url)}")
        repo_id = build_repo_id(repo_id_url)

        # --- Build Repo Graph ---
        logger.debug(f"[{ingestion_id}] Building RepoGraph...")
        builder = RepoGraphBuilder(repo_root=Path(repo_path), ingestion_id=str(ingestion_id))
        repo_graph = builder.build()
        logger.debug(f"[{ingestion_id}] RepoGraph built successfully")

        logger.debug(f"[{ingestion_id}] Total entities: {len(repo_graph.all_entities())}")
        # --- Persist Nodes & Relationships ---
        persistence = CodebaseGraphPersistence(session=session)
        nodes = repo_graph.all_entities()  # ✅ CORRECT method
        logger.debug(f"[{ingestion_id}] Sample node keys: {nodes[0].keys() if nodes else 'NO NODES'}")
        persistence.upsert_nodes(repo_id = repo_id, nodes=nodes)

        ## Relationships will be added in MS5 - skip for now
        persistence.upsert_relationships(repo_id = repo_id, relationships=repo_graph.relationships)

        # --- Run embeddings via IngestionPipeline ---
        settings = get_settings()
        provider = settings.EMBEDDING_PROVIDER
        pipeline = _build_pipeline(provider)

        # Corrected embedding loop with document_id lookup
        for node in nodes:
            logger.debug(f"[{ingestion_id}] Embedding node id={node.get('id')} keys={node.keys()}")
            text = node.get("text", "")
            if text.strip():
                canonical_id = node["canonical_id"]

                # Get the existing document_id from DB using canonical_id
                doc_node = persistence.get_node_by_canonical_id(repo_id, canonical_id)

                if doc_node:
                    # Proceed with embedding and persistence
                    chunks = pipeline._chunk(text, "code", provider)
                    # Inject canonical_id into every chunk metadata here
                    # This is what extract_canonical_ids_from_chunks() reads in rag_orchestrator
                    for chunk in chunks:
                        chunk.metadata["canonical_id"] = canonical_id
                        chunk.metadata["repo_id"] = repo_id
                        chunk.metadata["relative_path"] = node.get("relative_path", "")
                        chunk.metadata["doc_type"] = node.get("doc_type", "code")
                        chunk.metadata["source_metadata"] = {          # keep source_metadata too
                            **chunk.metadata.get("source_metadata", {}),
                            "canonical_id": canonical_id,
                        }

                    embeddings = pipeline._embed(chunks)
                    pipeline._persist(chunks, embeddings, str(ingestion_id), doc_node.document_id)
                else:
                    logger.warning(f"Skipping node without DB record: {canonical_id}")
            else:
                logger.debug(f"[{ingestion_id}] Skipping node without text")

        StatusManager(session).mark_completed(ingestion_id)
        logger.info(f"✅ Repo ingestion completed: {ingestion_id}")

    except Exception as exc:
        logger.exception(f"❌ Repo ingestion failed: {ingestion_id}")
        StatusManager(session).mark_failed(ingestion_id, error=str(exc))

    finally:
        if temp_dir:
            shutil.rmtree(temp_dir)
        session.close()


# -----------------------------
# POST /v1/codebase/ingest-repo
# -----------------------------
@router.post("/ingest-repo", response_model=RepoIngestResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_repo(
    git_url: str | None = Form(default=None),
    local_path: str | None = Form(default=None),
    provider: str | None = Form(default=None),
) -> RepoIngestResponse:
    if not git_url and not local_path:
        raise HTTPException(status_code=400, detail="Must provide either git_url or local_path")

    ingestion_id = uuid4()
    with SessionLocal() as session:
        StatusManager(session).create_request(
            ingestion_id=ingestion_id,
            source_type="repo",
            metadata={"git_url": git_url, "local_path": local_path, "provider": provider},
        )

    # Fire-and-forget background ingestion
    threading.Thread(
        target=_background_ingest_repo,
        kwargs={
            "ingestion_id": ingestion_id,
            "git_url": git_url,
            "local_path": local_path,
            "provider": provider,
        },
        daemon=True,
    ).start()

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
        request = session.query(IngestionRequest).filter_by(ingestion_id=ingestion_uuid).first()
        if not request:
            raise HTTPException(status_code=404, detail="Ingestion ID not found")

        return RepoIngestResponse(ingestion_id=request.ingestion_id, status=request.status)

