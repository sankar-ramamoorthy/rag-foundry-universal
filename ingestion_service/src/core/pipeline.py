# ingestion_service/src/core/pipeline.py - MS6 COMPLETE (both run() + run_with_chunks)
from __future__ import annotations
from typing import Any, Optional
import logging
from uuid import uuid4, uuid5, UUID, NAMESPACE_DNS

from shared.chunks import Chunk
from shared.chunkers.base import BaseChunker
from shared.chunkers.selector import ChunkerFactory
from src.core.database_session import get_sessionmaker
from src.core.crud.crud_document_node import create_document_node
from src.core.crud.document_relationships import create_document_relationship
from src.core.extractors.markdown_extractor import MarkdownSectionExtractor

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Orchestrates the ingestion pipeline: validate → chunk → embed → persist.

    Two entry points:
    - run(): For text-based ingestion (extracts, chunks, embeds, persists)
    - run_with_chunks(): For pre-chunked content like PDFs (embeds, persists)
    """

    def __init__(
        self,
        *,
        validator,
        chunker: Optional[BaseChunker] = None,
        embedder,
        vector_store,
    ) -> None:
        self._validator = validator
        self._chunker = chunker
        self._embedder = embedder
        self._vector_store = vector_store

    def run(
        self,
        *,
        text: str,
        ingestion_id: str,
        source_type: str,
        provider: str,
        filename: str = "unknown",  # NEW: Optional filename
        doc_type: str = "file",       # ADD
    ) -> None:
        """
        Full pipeline: validate → chunk → embed → persist + DocumentNode (MS6).

        Use this for simple text ingestion (TXT files).
        """
        logger.debug("🔄 pipeline.py run() - TEXT PATH - Full MS6 pipeline: validate → chunk → DocumentNode → embed → persist")
        
        # MS6: Create DocumentNode FIRST (before any vectors)
        sessionmaker = get_sessionmaker()
        with sessionmaker() as session:
            document_id = uuid4()
            # 🔥 MS7 FIX: Use exact source format that summary.py expects
            source = f"file_document_{ingestion_id}"  # Full UUID to match summary.py
            title = f"{source_type}_document_{ingestion_id[:8]}"  # Keep title human-readable
            
            logger.debug(f"📝 MS6 run() Creating DocumentNode:")
            logger.debug(f"   ingestion_id: {ingestion_id}")
            logger.debug(f"   document_id: {document_id}")
            logger.debug(f"   title: '{title}'")
            logger.debug(f"   source: '{source}'")  # 🔥 MS7: This MUST match summary.py query
            relative_path = filename or "uploaded_file"
            canonical_id = f"{source_type}_document_{ingestion_id}"            
            create_document_node(
                session,
                document_id=document_id,
                title=title,
                summary="Document summary pending MS7",
                source=source,  # 🔥 MS7: Matches summary.py query
                ingestion_id=UUID(ingestion_id),
                doc_type=source_type,  # "file", "image", etc.
                canonical_id=canonical_id,
                relative_path=relative_path,
                repo_id=str(ingestion_id), 
            )
            session.commit()  #  CRITICAL: Commit BEFORE vectors
            logger.debug(f"✅ MS6 run() DocumentNode COMMITTED {document_id} for {ingestion_id}")
            logger.debug(f"   → summary.py will look for source='{source}'")

        # Continue normal pipeline
        self._validate(text)
        chunks = self._chunk(
            text=text,
            source_type=source_type,
            provider=provider,
            doc_type=doc_type or source_type,         # ADD
            relative_path=relative_path,              # ADD
            canonical_id=canonical_id,                # ADD
        )
        embeddings = self._embed(chunks)
        logger.debug(f"📦 MS6 run() Persisting {len(chunks)} chunks with document_id={document_id}")
        self._persist(chunks, embeddings, ingestion_id, str(document_id))

    def run_with_chunks(
        self,
        *,
        chunks: list[Chunk],
        ingestion_id: str,
        filename: str = "unknown",  # NEW: Optional filename
        doc_type: str = "file",       # ADD
    ) -> None:
        """
        Pipeline for pre-chunked content: DocumentNode → embed → persist (MS6).
        Use this for PDFs or other content where chunking happened upstream.
        """
        logger.debug(f"🔄 pipeline.py run_with_chunks() - PDF PATH - {len(chunks)} pre-chunked items")
        
        # MS6: Create DocumentNode FIRST
        sessionmaker = get_sessionmaker()
        with sessionmaker() as session:
            document_id = uuid4()
            # 🔥 MS7 FIX: Use exact source format that summary.py expects
            source = f"file_document_{ingestion_id}"  # Full UUID to match summary.py
            title = chunks[0].metadata.get("filename", "untitled") if chunks else "untitled"
            
            logger.debug(f"📝 MS6 run_with_chunks() Creating DocumentNode:")
            logger.debug(f"   ingestion_id: {ingestion_id}")
            logger.debug(f"   document_id: {document_id}")
            logger.debug(f"   title: '{title}'")
            logger.debug(f"   source: '{source}'")  # 🔥 MS7: This MUST match summary.py query
            relative_path = filename or "uploaded_file"
            canonical_id = f"pdf_document_{ingestion_id}"            
            create_document_node(
                session,
                document_id=document_id,
                title=title,
                summary="Document summary pending MS7",
                source=source,  # 🔥 MS7: Matches summary.py query
                ingestion_id=UUID(ingestion_id),
                doc_type="file",
                canonical_id=canonical_id,
                relative_path=relative_path,            
                repo_id=str(ingestion_id), 
                )
            session.commit()  # 🔥 CRITICAL: Commit BEFORE vectors
            logger.debug(f"✅ MS6 run_with_chunks() DocumentNode COMMITTED {document_id} for {ingestion_id}")
            logger.debug(f"   → summary.py will look for source='{source}'")

            # Inject metadata into pre-built chunks — these bypass _chunk()
        for chunk in chunks:
            chunk.metadata.setdefault("source_type", "file")
            chunk.metadata.setdefault("doc_type", doc_type or "file")      # ADD
            chunk.metadata.setdefault("provider", "unknown")
            chunk.metadata.setdefault("relative_path", relative_path)      # ADD
            chunk.metadata.setdefault("canonical_id", canonical_id)        # ADD
            chunk.metadata.setdefault("chunk_strategy", 
            chunk.metadata.get("chunk_strategy", "unknown"))
        
        # Continue pipeline
        embeddings = self._embed(chunks)
        logger.debug(f"📦 MS6 run_with_chunks() Persisting {len(chunks)} chunks with document_id={document_id}")
        self._persist(chunks, embeddings, ingestion_id, str(document_id))

    def _validate(self, text: str) -> None:
        """Validate input text (currently no-op)."""
        logger.debug("✅ pipeline.py _validate() - No-op validator passed")

    def _chunk(
        self,
        text: str,
        source_type: str,
        provider: str,
        doc_type: str = "file",       # ADD
        relative_path: str = "",      # ADD
        canonical_id: str = "",       # ADD
    ) -> list[Chunk]:
        """
        Chunk text using selected strategy.
        Adds provenance metadata to each chunk for provenance.
        """
        logger.debug(f"🔪 pipeline.py _chunk() text_len={len(text)} source_type={source_type}")
        
        if self._chunker is None:
            selected_chunker, chunker_params = ChunkerFactory.choose_strategy(text)
        else:
            selected_chunker = self._chunker
            chunker_params = {}

        chunks: list[Chunk] = selected_chunker.chunk(text, **chunker_params)
        chunk_strategy = getattr(selected_chunker, "chunk_strategy", "unknown")

        logger.debug(f"   → Selected chunker: {getattr(selected_chunker, 'name', selected_chunker.__class__.__name__)}")
        logger.debug(f"   → Strategy: {chunk_strategy}, Chunks produced: {len(chunks)}")

        # Add provenance metadata to each chunk
        for i, chunk in enumerate(chunks):
            chunk.metadata.update(
                {
                    "chunk_strategy": chunk_strategy,
                    "chunker_name": getattr(
                        selected_chunker,
                        "name",
                        selected_chunker.__class__.__name__,
                    ),
                    "chunker_params": dict(chunker_params),
                    "source_type": source_type,
                    "provider": provider,
                    "doc_type": doc_type or source_type or "unknown",      # ADD
                    "relative_path": relative_path or "",                  # ADD
                    "canonical_id": canonical_id or "",                    # ADD
                }
            )
            logger.debug(f"   → Chunk {i}: {len(chunk.content)} chars")

        return chunks

    def _embed(self, chunks: list[Chunk]) -> list[Any]:
        """
        Generate embeddings for chunks.
        Validates that embedding count matches chunk count.
        """
        logger.debug(f"🔗 pipeline.py _embed() {len(chunks)} chunks")
        embeddings = self._embedder.embed(chunks)

        if len(embeddings) != len(chunks):
            raise ValueError(
                f"Embedder mismatch: {len(chunks)} chunks, {len(embeddings)} embeddings"
            )

        logger.debug(f"✅ _embed() produced {len(embeddings)} embeddings ({len(embeddings[0])} dims each)")
        return embeddings

    def _persist(
        self,
        chunks: list[Chunk],
        embeddings: list[Any],
        ingestion_id: str,
        document_id: str,  # MS6-IS1: Link chunks to DocumentNode
    ) -> None:
        """
        Persist chunks and embeddings to vector store.
        """
        logger.debug(f"💾 pipeline.py _persist() {len(chunks)} chunks doc_id={document_id}")
        logger.debug(f"   → ingestion_id: {ingestion_id}")
        self._vector_store.persist(
            chunks=chunks,
            embeddings=embeddings,
            ingestion_id=ingestion_id,
            document_id=document_id,  # MS6-IS1: Pass to vector store
        )
        logger.debug(f"✅ _persist() COMPLETE for doc_id={document_id}")



    def run_with_sections(
        self,
        *,
        source: str,
        ingestion_id: str,
        filename: str = "unknown",
        doc_type: str = "markdown_module",
    ) -> None:
        """
        Pipeline for uploaded .md files.
        Extracts sections → creates DocumentNode per section
        → persists DEFINES relationships → embeds + persists vectors.
        """
        logger.debug(
            f"🔄 run_with_sections() - MARKDOWN PATH - "
            f"file={filename} ingestion_id={ingestion_id}"
        )

        extractor = MarkdownSectionExtractor(relative_path=filename)
        artifacts = extractor.extract(source)

        sessionmaker = get_sessionmaker()

        # Step 1: Create DocumentNode for each artifact
        # Build canonical_id → document_id map for relationship wiring
        canonical_to_doc_id: dict = {}

        with sessionmaker() as session:
            for artifact in artifacts:
                document_id = uuid4()
                canonical_id = artifact["id"]
                artifact_doc_type = artifact.get("doc_type", doc_type)

                create_document_node(
                    session,
                    document_id=document_id,
                    title=artifact.get("name", filename),
                    summary="Document summary pending",
                    source=f"file_document_{ingestion_id}",
                    ingestion_id=UUID(ingestion_id),
                    doc_type=artifact_doc_type,
                    canonical_id=canonical_id,
                    relative_path=filename,
                    repo_id=str(ingestion_id),
                )

                canonical_to_doc_id[canonical_id] = str(document_id)
                logger.debug(
                    f"   → DocumentNode: {artifact_doc_type} "
                    f"canonical={canonical_id[:40]} doc_id={document_id}"
                )

            session.commit()
            logger.debug(
                f"✅  {len(artifacts)} DocumentNodes committed "
                f"for ingestion_id={ingestion_id}"
            )

        # Step 2: Create DEFINES relationships
        # parent_id in artifact → from_document_id DEFINES to_document_id
        with sessionmaker() as session:
            rel_count = 0
            for artifact in artifacts:
                parent_canonical = artifact.get("parent_id")
                if not parent_canonical:
                    continue  # MODULE node has no parent

                from_doc_id = canonical_to_doc_id.get(parent_canonical)
                to_doc_id = canonical_to_doc_id.get(artifact["id"])

                if not from_doc_id or not to_doc_id:
                    logger.warning(
                        f"   ⚠️ Missing doc_id for relationship: "
                        f"{parent_canonical} → {artifact['id']}"
                    )
                    continue

                create_document_relationship(
                    session,
                    from_document_id=from_doc_id,
                    to_document_id=to_doc_id,
                    relation_type="DEFINES",
                    metadata={"artifact_type": artifact.get("artifact_type", "")},
                )
                rel_count += 1

            session.commit()
            logger.debug(f"✅ MS6-IS3: {rel_count} DEFINES relationships committed")

        # Step 3: Embed and persist vectors for each artifact
        chunks_to_embed = []
        doc_ids_for_chunks = []

        for artifact in artifacts:
            text = artifact.get("text", "").strip()
            if not text:
                continue

            chunk = Chunk(
                chunk_id=str(uuid5(UUID(ingestion_id), artifact["id"])), 
                content=text,
                metadata={
                    "source_type": "file",
                    "doc_type": artifact.get("doc_type", doc_type),
                    "canonical_id": artifact["id"],
                    "relative_path": filename,
                    "artifact_type": artifact.get("artifact_type", ""),
                    "provider": self._embedder.__class__.__name__,
                }
            )
            chunks_to_embed.append(chunk)
            doc_ids_for_chunks.append(canonical_to_doc_id[artifact["id"]])

        if chunks_to_embed:
            embeddings = self._embed(chunks_to_embed)
            logger.debug(
                f"📦  Persisting {len(chunks_to_embed)} "
                f"section chunks for ingestion_id={ingestion_id}"
            )
            # Persist each chunk with its own document_id
            for chunk, embedding, doc_id in zip(
                chunks_to_embed, embeddings, doc_ids_for_chunks
            ):
                self._persist([chunk], [embedding], ingestion_id, doc_id)
        else:
            logger.warning("⚠️  No text content found in any section")

        logger.debug(f"✅  run_with_sections() COMPLETE for {filename}")