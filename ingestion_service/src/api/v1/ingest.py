# ingestion_service/src/api/v1/ingest.py
from uuid import uuid4, UUID
import json
import logging
import threading
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status
from src.api.v1.models import IngestResponse
from src.core.database_session import get_sessionmaker
from src.core.models import IngestionRequest
from src.core.pipeline import IngestionPipeline
from src.core.status_manager import StatusManager
from src.core.http_vectorstore import HttpVectorStore
from src.core.config import get_settings
from shared.embedders.factory import get_embedder
from src.core.ocr.ocr_factory import get_ocr_engine
from src.core.extractors.pdf import PDFExtractor
from src.core.document_graph.builder import DocumentGraphBuilder
from src.core.chunk_assembly.pdf_chunk_assembler import PDFChunkAssembler
from src.core.converters.docling_converter import DoclingConverter, is_docling_supported  # IS4

SessionLocal = get_sessionmaker()
router = APIRouter(tags=["ingestion"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# File type classification
# IS4: rich docs routed through Docling → MarkdownSectionExtractor
# IS5: tabular docs routed through Docling → flat chunking
# -----------------------------
RICH_DOC_EXTENSIONS = {".docx", ".pptx", ".html", ".htm", ".epub"}  # IS4
TABULAR_EXTENSIONS = {".xlsx", ".csv"}                                # IS5


def _get_extension(filename: str) -> str:
    return f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""


# -----------------------------
# Helpers
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
        base_url=settings.VECTOR_STORE_SERVICE_URL, provider=provider
    )
    return IngestionPipeline(
        validator=NoOpValidator(),
        embedder=embedder,
        vector_store=vector_store,
    )


def extract_text_from_bytes(
    file_bytes: bytes, filename: str, content_type: str,
    ocr_provider: Optional[str]
) -> str:
    # Images → OCR
    if content_type.startswith("image/") or filename.lower().endswith(
        (".png", ".jpg", ".jpeg", ".tiff")
    ):
        logger.info(f"🖼️ OCR processing: {filename}")
        ocr_engine = get_ocr_engine(ocr_provider or "tesseract")
        return ocr_engine.extract_text(file_bytes) or ""

    # Text files → robust multi-encoding decoder
    encodings = ["utf-8", "utf-8-sig", "windows-1252", "latin-1", "cp1252", "iso-8859-1"]
    for encoding in encodings:
        try:
            text = file_bytes.decode(encoding)
            logger.debug(f"✅ Decoded {filename} as {encoding}")
            return text
        except UnicodeDecodeError:
            continue

    # Final fallback
    logger.warning(f"⚠️ Using fallback decoder for {filename}")
    return file_bytes.decode("latin-1", errors="ignore")

def _ingest_pdf_pymupdf(
    *,
    pipeline: IngestionPipeline,
    file_bytes: bytes,
    filename: str,
    ingestion_id: UUID,
    doc_type: str,
) -> None:
    """
    PyMuPDF fallback for PDF ingestion.
    Used when DOCLING_ENABLED=False or Docling conversion fails.
    """
    pdf_extractor = PDFExtractor()
    artifacts = pdf_extractor.extract(
        file_bytes=file_bytes, source_name=filename
    )
    graph = DocumentGraphBuilder().build(artifacts)
    chunks = PDFChunkAssembler().assemble(graph)
    if not chunks:
        raise RuntimeError("No extractable text found in uploaded PDF")
    pipeline.run_with_chunks(
        chunks=chunks,
        ingestion_id=str(ingestion_id),
        filename=filename,
        doc_type=doc_type,
    )

# -----------------------------
# Background ingestion
# -----------------------------
def background_ingest_file(
    *, ingestion_id: UUID, file_bytes: bytes,
    filename: str, content_type: str, metadata: dict
):
    settings = get_settings()
    provider = settings.EMBEDDING_PROVIDER
    pipeline = _build_pipeline(provider)

    ext = _get_extension(filename)

    # IS4: file type classification
    is_pdf      = filename.endswith(".pdf") or content_type == "application/pdf"
    is_image    = content_type.startswith("image/") or \
                  filename.lower().endswith((".png", ".jpg", ".jpeg", ".tiff"))
    is_markdown = ext == ".md"
    is_rich_doc = ext in RICH_DOC_EXTENSIONS   #  DOCX, PPTX, HTML, EPUB
    is_tabular  = ext in TABULAR_EXTENSIONS    #  XLSX, CSV

    # doc_type mapping
    if is_pdf:
        doc_type = "pdf"
    elif is_image:
        doc_type = "image"
    elif is_markdown:
        doc_type = "markdown_module"
    elif is_rich_doc:
        doc_type = "markdown_module"   # becomes structured markdown after Docling
    elif is_tabular:
        doc_type = "tabular"           # 
    else:
        doc_type = "file"

    ocr_provider = metadata.get("ocr_provider")

    with SessionLocal() as session:
        StatusManager(session).mark_running(ingestion_id)

    try:
        # ------------------------------------------------------------------
        # PDF — Docling primary, PyMuPDF fallback  
        # ------------------------------------------------------------------
        if is_pdf:
            if settings.DOCLING_ENABLED:
                logger.info(f"📄 IS6: Docling PDF conversion: {filename}")
                try:
                    converter = DoclingConverter()
                    markdown_text = converter.convert(
                        file_bytes=file_bytes, filename=filename
                    )
                    if not markdown_text.strip():
                        raise RuntimeError(
                            f"Docling produced empty output for {filename}"
                        )
                    logger.info(
                        f"IS6: {filename} → {len(markdown_text)} chars Markdown "
                        f"→ MarkdownSectionExtractor"
                    )
                    pipeline.run_with_sections(
                        source=markdown_text,
                        ingestion_id=str(ingestion_id),
                        filename=filename,
                        doc_type=doc_type,
                    )
                except Exception as docling_exc:
                    logger.warning(
                        f"⚠️ IS6: Docling failed for {filename} "
                        f"({docling_exc}) — falling back to PyMuPDF"
                    )
                    _ingest_pdf_pymupdf(
                        pipeline=pipeline,
                        file_bytes=file_bytes,
                        filename=filename,
                        ingestion_id=ingestion_id,
                        doc_type=doc_type,
                    )
            else:
                logger.info(f"📄 IS6: PyMuPDF path (Docling disabled): {filename}")
                _ingest_pdf_pymupdf(
                    pipeline=pipeline,
                    file_bytes=file_bytes,
                    filename=filename,
                    ingestion_id=ingestion_id,
                    doc_type=doc_type,
                )

        # ------------------------------------------------------------------
        # Markdown — structured section extraction  
        # ------------------------------------------------------------------
        elif is_markdown:
            text = extract_text_from_bytes(
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
                ocr_provider=None,
            )
            if not text.strip():
                raise RuntimeError("No extractable text found in uploaded Markdown file")
            pipeline.run_with_sections(
                source=text,
                ingestion_id=str(ingestion_id),
                filename=filename,
                doc_type=doc_type,
            )

        # ------------------------------------------------------------------
        # Rich documents — Docling → Markdown → section extraction
        # DOCX, PPTX, HTML, EPUB
        # ------------------------------------------------------------------
        elif is_rich_doc:
            logger.info(f"📄 IS4: Docling rich doc conversion: {filename}")
            converter = DoclingConverter()
            markdown_text = converter.convert(
                file_bytes=file_bytes, filename=filename
            )
            if not markdown_text.strip():
                raise RuntimeError(
                    f"Docling produced empty output for {filename}"
                )
            logger.info(
                f"IS4: {filename} → {len(markdown_text)} chars Markdown "
                f"→ MarkdownSectionExtractor"
            )
            pipeline.run_with_sections(
                source=markdown_text,
                ingestion_id=str(ingestion_id),
                filename=filename,
                doc_type=doc_type,
            )

        # ------------------------------------------------------------------
        # Tabular — Docling → Markdown → flat chunking
        # XLSX, CSV (no heading hierarchy)
        # ------------------------------------------------------------------
        elif is_tabular:
            logger.info(f"📊 IS5: Docling tabular conversion: {filename}")
            converter = DoclingConverter()
            markdown_text = converter.convert(
                file_bytes=file_bytes, filename=filename
            )
            if not markdown_text.strip():
                raise RuntimeError(
                    f"Docling produced empty output for {filename}"
                )
            logger.info(
                f"IS5: {filename} → {len(markdown_text)} chars Markdown "
                f"→ flat chunking"
            )
            pipeline.run(
                text=markdown_text,
                ingestion_id=str(ingestion_id),
                source_type="file",
                provider=provider,
                filename=filename,
                doc_type=doc_type,
            )

        # ------------------------------------------------------------------
        # Everything else — flat text chunking
        # ------------------------------------------------------------------
        else:
            text = extract_text_from_bytes(
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
                ocr_provider=ocr_provider,
            )
            if not text.strip():
                raise RuntimeError("No extractable text found in uploaded file")
            pipeline.run(
                text=text,
                ingestion_id=str(ingestion_id),
                source_type="file",
                provider=provider,
                filename=filename,
                doc_type=doc_type,
            )

        # ------------------------------------------------------------------
        # Mark completed + trigger summary
        # ------------------------------------------------------------------
        with SessionLocal() as session:
            StatusManager(session).mark_completed(ingestion_id)

        summary_url = f"http://llm_service:8000/v1/summarize/{ingestion_id}"
        try:
            httpx.post(summary_url, timeout=1000)
            logger.info(f"✅ Summary task dispatched: {summary_url}")
        except Exception as e:
            logger.warning(f"⚠️ Summary dispatch failed: {e}")

    except Exception as exc:
        with SessionLocal() as session:
            StatusManager(session).mark_failed(ingestion_id, error=str(exc))
        logger.error(f"❌ Background ingestion failed: {ingestion_id} - {exc}")


# -----------------------------
# API endpoints
# -----------------------------
@router.post(
    "/ingest/file",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED
)
def ingest_file(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(default=None)
) -> IngestResponse:
    try:
        parsed_metadata = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON") from exc

    ingestion_id = uuid4()
    file_bytes = file.file.read()
    filename = file.filename or "unknown"
    content_type = file.content_type or "application/octet-stream"

    with SessionLocal() as session:
        StatusManager(session).create_request(
            ingestion_id=ingestion_id,
            source_type="file",
            metadata=parsed_metadata
        )

    threading.Thread(
        target=background_ingest_file,
        kwargs={
            "ingestion_id": ingestion_id,
            "file_bytes": file_bytes,
            "filename": filename,
            "content_type": content_type,
            "metadata": parsed_metadata,
        },
        daemon=True,
    ).start()

    return IngestResponse(ingestion_id=ingestion_id, status="accepted")


@router.get("/ingest/{ingestion_id}", response_model=IngestResponse)
def ingest_status(ingestion_id: str) -> IngestResponse:
    try:
        ingestion_uuid = UUID(ingestion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ingestion ID format")

    with SessionLocal() as session:
        request = session.query(IngestionRequest).filter_by(
            ingestion_id=ingestion_uuid
        ).first()
        if request is None:
            raise HTTPException(status_code=404, detail="Ingestion ID not found")

        return IngestResponse(
            ingestion_id=request.ingestion_id,
            status=request.status
        )