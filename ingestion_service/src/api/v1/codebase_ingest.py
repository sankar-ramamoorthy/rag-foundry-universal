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
from src.core.codebase.structural_inventory import (
    build_structural_inventory,
    inventory_to_graph_dicts,
)
from src.core.pipeline import IngestionPipeline

from src.core.config import get_settings
from shared.chunkers.selector import ChunkerFactory
from shared.embedders.factory import get_embedder
from src.core.http_vectorstore import HttpVectorStore
from src.core.codebase.identity import build_repo_id
from src.core.codebase.snapshot_diff import classify as classify_snapshot_diff
from src.core.repo_naming import derive_repo_identity
from src.core.codebase.embedding_buffer import EmbeddingBuffer
from src.core.codebase.language import language_for_path
from src.core.config import Settings
from src.core import db_utils
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
    # Issue #196 (FR-005a): bypass reuse classification, always full.
    force_full_rebuild: bool = False


class RepoIngestResponse(BaseModel):
    ingestion_id: UUID
    status: str
    embed_progress: dict | None = None


def _chunk_and_buffer_node(pipeline, buffer, node, repo_id: str, provider: str) -> None:
    """Chunk+embed one node not eligible for reuse (T024's re-embed path)."""
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


def _retag_reused_vectors(
    pipeline: IngestionPipeline, document_ids: list[str], ingestion_id: str,
) -> None:
    """Issue #196 (FR-007b, T024): bulk-carry reused artifacts' existing
    vectors forward to this generation's ingestion_id, no re-embedding."""
    if not document_ids:
        return
    retagged = pipeline._vector_store.retag_ingestion_id(document_ids, ingestion_id)
    logger.info(
        f"Re-tagged {retagged} reused vector row(s) "
        f"({len(document_ids)} artifact(s)) to ingestion {ingestion_id}"
    )


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
    eligible_relative_paths: frozenset = frozenset(),
) -> tuple[int, int]:
    """Page persisted artifacts; bound chunk and vector state independently.

    Missing/replaced nodes fail the attempt instead of silently losing evidence.
    Return shape retains the legacy skipped counter, now necessarily zero.

    Issue #196 (FR-006/FR-007, T024): a node whose *file* is in
    eligible_relative_paths skips chunk+embed entirely -- its existing
    vectors (still valid, R1 keeps document_id stable) are bulk re-tagged
    to this generation's ingestion_id instead, once, after paging
    completes. Default empty set preserves today's exact full-ingestion
    behavior (every node re-embedded) — required non-regression for the
    no-prior-generation case.
    """
    progress: dict = {
        "stage": "embedding", "nodes_processed": 0, "nodes_total": 0,
        "chunks_persisted": 0, "max_buffer_chunks": 0, "max_buffer_bytes": 0,
    }
    report_progress(dict(progress))  # BEFORE preflight/count/page allocation.

    # Issue #196 (R1): persist_graph now preserves document_id for a
    # canonical_id whose node row survives across generations, instead of
    # always minting a fresh one. Every node is still fully re-embedded
    # here (no skip logic yet), so make this step idempotent per
    # ingestion_id: clear any vectors already tagged with this run's
    # ingestion_id before writing fresh ones. A no-op for the normal case
    # (a fresh ingestion_id has no rows yet); guards a retried/duplicate
    # invocation of the same generation against leaving stale vector rows
    # behind for a reused document_id, where cascade-on-delete no longer
    # fires because the node itself was never deleted.
    pipeline._vector_store.delete_by_ingestion_id(ingestion_id)

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

    retag_document_ids: list[str] = []

    def append_page(page):
        # Frame exit drops the last artifact's text/chunk-list references.
        for node in page:
            if not (node.text or "").strip():
                continue
            if node.relative_path in eligible_relative_paths:
                # FR-006/FR-007: content + chunking + embedding config all
                # match the prior generation -- carry the existing vectors
                # forward instead of re-chunking/re-embedding.
                retag_document_ids.append(str(node.document_id))
            else:
                _chunk_and_buffer_node(pipeline, buffer, node, repo_id, provider)
            progress["nodes_processed"] += 1

    for page in pages():
        append_page(page)
        del page  # Do not retain predecessor page during generator advancement.
        acknowledged()
    if progress["nodes_processed"] != progress["nodes_total"]:
        raise RuntimeError("Embeddable artifact count changed during embedding")
    buffer.flush()
    acknowledged()
    _retag_reused_vectors(pipeline, retag_document_ids, ingestion_id)
    return buffer.chunks_persisted, 0


def _build_and_persist_graph(
    repo_path, repo_id, ingestion_id, persistence, report_stage,
):
    """Own all graph/IR references in a frame that ends before embedding.

    Issue #196 (T023): also extracts this generation's file-level content
    hashes from the graph before it goes out of scope, so the caller can
    classify a snapshot diff without retaining the graph/builder past this
    function (#160's memory discipline -- see
    test_background_worker_releases_builder_and_graph_before_embedding).

    Issue #197 (ORIENT): also builds the deterministic structural inventory
    here, in the same scope as the symbol graph, BEFORE the one
    persist_graph() call below -- not after it returns. persist_graph
    deletes any canonical_id absent from the node set it's given, so the
    symbol graph's nodes and the inventory's nodes/relationships MUST be
    merged into that single call; two separate persist_graph calls would
    have the second delete every node the first just wrote.
    """
    report_stage("graph_build")
    builder = RepoGraphBuilder(
        repo_root=Path(repo_path), ingestion_id=str(ingestion_id),
    )
    graph = builder.build()
    current_file_hashes = {
        entity["canonical_id"]: entity["content_hash"]
        for entity in graph.all_entities()
        if entity.get("content_hash") is not None
    }

    report_stage("structural_inventory")
    indexed_paths = set(graph.files.keys())
    inventory = build_structural_inventory(
        Path(repo_path), indexed_paths=indexed_paths,
    )
    inventory_nodes, inventory_relationships = inventory_to_graph_dicts(
        str(ingestion_id), inventory, indexed_paths, Path(repo_path),
    )

    report_stage("graph_persist")
    stats = persistence.persist_graph(
        repo_id=repo_id,
        nodes=graph.all_entities() + inventory_nodes,
        relationships=graph.relationships + inventory_relationships,
    )
    return stats, current_file_hashes, inventory


def _resolve_reuse_eligibility(
    session, ingestion_id: UUID, repo_id: str, force_full_rebuild: bool,
) -> tuple[str | None, bool, dict, bool]:
    """Issue #196 (T020/T021/T025/R4/R6): resolve this generation's lineage
    and FR-006 reuse-gate identity, before cloning/graph build begins, and
    record the lineage fields that are known immediately.

    Returns (prior_generation_id, is_incremental, prior_file_hashes,
    config_matches). prior_generation_id is set for lineage whenever a
    prior generation existed, regardless of force_full_rebuild (data-
    model.md) -- it is not itself a "reuse is possible" signal; only
    is_incremental=True means FR-004's classification actually runs.
    """
    prior_generation_id = db_utils.resolve_current_generation(repo_id)
    is_incremental = prior_generation_id is not None and not force_full_rebuild

    settings = get_settings()
    chunking_config_version = ChunkerFactory.VERSION
    embedding_config_version = (
        f"{settings.EMBEDDING_PROVIDER}:{settings.OLLAMA_EMBED_MODEL}"
    )
    StatusManager(session).record_generation_start(
        ingestion_id,
        parent_generation_id=prior_generation_id,
        chunking_config_version=chunking_config_version,
        embedding_config_version=embedding_config_version,
    )

    prior_hashes: dict = {}
    config_matches = False
    if is_incremental:
        prior_hashes = db_utils.file_content_hashes(repo_id, prior_generation_id)
        prior_chunking_version, prior_embedding_version = (
            db_utils.generation_config_versions(prior_generation_id)
        )
        config_matches = (
            prior_chunking_version == chunking_config_version
            and prior_embedding_version == embedding_config_version
        )
        if not config_matches:
            logger.info(
                f"[{ingestion_id}] Chunking/embedding config changed since "
                f"generation {prior_generation_id[:8]} "
                f"({prior_chunking_version!r}/{prior_embedding_version!r} -> "
                f"{chunking_config_version!r}/{embedding_config_version!r}); "
                "every file will be re-embedded"
            )

    return prior_generation_id, is_incremental, prior_hashes, config_matches


# -----------------------------
# Background ingestion worker
# -----------------------------
def _background_ingest_repo(
    ingestion_id: UUID,
    git_url: str | None,
    local_path: str | None,
    provider: str | None,
    force_full_rebuild: bool = False,
):
    """
    Clone or use local repo, build graph, persist nodes &
    relationships, and embed code artifacts.

    Issue #196: automatically incremental (FR-004) when a valid prior
    completed generation exists for this repo_id and force_full_rebuild is
    not set (FR-005a) -- otherwise every file is treated as new, exactly
    matching today's full-ingestion behavior (Required Non-Regression).
    """
    session = SessionLocal()

    temp_dir = None
    try:
        StatusManager(session).mark_running(ingestion_id)
        logger.debug(f"[{ingestion_id}] Starting background ingestion")
        logger.debug(
            f"[{ingestion_id}] git_url={git_url}, local_path={local_path}, "
            f"provider={provider}, force_full_rebuild={force_full_rebuild}"
        )

        repo_id_url = git_url or local_path
        if not repo_id_url:
            raise ValueError("Either git_url or local_path must be provided")
        repo_id = build_repo_id(repo_id_url)
        logger.debug(f"build_repo_id({repo_id_url}) calculates repo_id = {repo_id}")

        # T020/T021/T025/R6 (#196): resolve lineage + FR-006 reuse-gate
        # identity before cloning -- repo_id is a pure function of the
        # source URL/path, no checkout needed.
        _prior_generation_id, is_incremental, prior_hashes, config_matches = (
            _resolve_reuse_eligibility(
                session, ingestion_id, repo_id, force_full_rebuild,
            )
        )

        # T030 (#196/R5): resolved only for a git-backed ingestion; stays
        # None for local_path (spec Non-Goals -- non-git sources are out
        # of scope for commit identity).
        commit_sha: str | None = None
        if git_url:
            import git  # GitPython
            temp_dir = tempfile.mkdtemp()
            logger.debug(f"Cloning {git_url} into {temp_dir}")
            cloned = git.Repo.clone_from(git_url, temp_dir)
            commit_sha = cloned.head.commit.hexsha
            cloned.close()  # release the git process/pack-file handles
            repo_path = temp_dir
        else:
            repo_path = str(Path(local_path).resolve())
            logger.info(f"[{ingestion_id}] Using local repo path: {repo_path}")

        persistence = CodebaseGraphPersistence(session=session)
        report_progress = partial(
            StatusManager(session).update_embed_progress, ingestion_id,
        )
        stats, current_hashes, inventory = _build_and_persist_graph(
            repo_path, repo_id, ingestion_id, persistence,
            lambda stage: report_progress({
                "stage": stage, "nodes_processed": 0, "nodes_total": 0,
                "chunks_persisted": 0, "max_buffer_chunks": 0, "max_buffer_bytes": 0,
            }),
        )
        logger.info(f"[{ingestion_id}] Graph persisted: {stats}")

        # T023 (#196): classify current vs. prior file fingerprints. A
        # config mismatch collapses the eligible set to empty -- FR-006's
        # all-or-nothing gate -- rather than calling classify() at all.
        eligible_relative_paths: frozenset = frozenset()
        if is_incremental and config_matches:
            diff = classify_snapshot_diff(current_hashes, prior_hashes)
            eligible_relative_paths = diff.unchanged
            logger.info(
                f"[{ingestion_id}] Snapshot diff: {len(diff.unchanged)} unchanged, "
                f"{len(diff.changed)} changed, {len(diff.new)} new, "
                f"{len(diff.deleted)} deleted"
            )

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
            eligible_relative_paths=eligible_relative_paths,
        )
        logger.info(
            f"[{ingestion_id}] Embedded {chunk_count} chunks "
            f"({skipped_missing} nodes had no DB record)"
        )

        # Issue #197 (ORIENT): record this generation's deterministic
        # structural facts, same "finalize this generation's metadata"
        # moment as the lineage recording below, before the terminal status
        # transition -- so structural_summary is populated before the
        # generation can ever be served as "ready".
        db_utils.record_structural_summary(ingestion_id, inventory.summary_dict())

        # T026/T030/T031 (#196): record whether reuse classification
        # actually ran and the resolved commit SHA, before the terminal
        # status transition.
        StatusManager(session).record_completion_lineage(
            ingestion_id, is_incremental=is_incremental, commit_sha=commit_sha,
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
            try:
                shutil.rmtree(temp_dir)
            except OSError:
                # A lingering git-process/pack-file handle (observed on
                # Windows) must not mask an otherwise-successful ingestion
                # by raising out of this finally block -- best-effort,
                # matches the superseded-generation cleanup pattern above.
                logger.warning(
                    f"[{ingestion_id}] Could not remove temp clone dir "
                    f"{temp_dir}; leaving it for OS temp cleanup",
                    exc_info=True,
                )
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
    force_full_rebuild: bool = Form(default=False),
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
            "force_full_rebuild": force_full_rebuild,
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
