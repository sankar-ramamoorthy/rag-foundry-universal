"""#160 Linux fresh-process RSS probe; requires isolated *_test DB and local vector API.

JSONL stdout is raw evidence. This uses the real graph builder, SQL paging and
HTTP persistence, but a deterministic 1024-D embedder, NOT Ollama or DocsGPT.
Only generated fixture IDs/files are removed. Never point at production data.
"""

import argparse
import json
import logging
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ingestion_service"))


class Sampler:
    def __init__(self):
        self.stage = "startup"
        self.started = time.monotonic()
        self.peaks = {}
        self.baselines = {}
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def emit(self, record):
        with self.lock:
            print(json.dumps(record), flush=True)

    def sample(self):
        with self.lock:
            fields = {}
            for line in Path("/proc/self/status").read_text().splitlines():
                if line.startswith(("VmRSS:", "VmHWM:")):
                    key, value, _ = line.split()
                    fields[key.rstrip(":")] = int(value) * 1024
            rss = fields["VmRSS"]
            self.baselines.setdefault(self.stage, rss)
            self.peaks[self.stage] = max(self.peaks.get(self.stage, 0), rss)
            cgroup = {}
            for name in ("memory.current", "memory.peak", "memory.max"):
                path = Path("/sys/fs/cgroup") / name
                cgroup[name] = path.read_text().strip() if path.exists() else None
            self.emit(
                {
                    "kind": "sample",
                    "seconds": time.monotonic() - self.started,
                    "stage": self.stage,
                    "rss_bytes": rss,
                    "hwm_bytes": fields["VmHWM"],
                    "cgroup_mount_root": cgroup,
                }
            )

    def set_stage(self, stage):
        with self.lock:
            self.stage = stage
            self.sample()  # Baseline precedes stage allocation, not after first page.

    def _run(self):
        while not self.stop.wait(0.02):
            self.sample()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, required=True)
    parser.add_argument("--payload-chars", type=int, default=1000)
    parser.add_argument("--vector-url", required=True)
    args = parser.parse_args()
    if platform.system() != "Linux":
        parser.error("This probe requires Linux /proc RSS measurements")
    if args.files <= 0 or args.payload_chars <= 0:
        parser.error("Fixture sizes must be positive")
    if urlparse(args.vector_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Use a local isolated test vector service")
    return args


def main():
    args = parse_args()

    from sqlalchemy import text
    from src.api.v1.codebase_ingest import (
        _build_and_persist_graph,
        _embed_repo_artifacts,
    )
    from src.core.config import Settings
    from src.core.database_session import get_engine, get_sessionmaker
    from src.core.models import IngestionRequest
    from src.core.status_manager import StatusManager
    from src.core.codebase.codebase_persistence import CodebaseGraphPersistence
    from src.core.http_vectorstore import HttpVectorStore
    from src.core.pipeline import IngestionPipeline
    from shared.models.document_node import DocumentNode

    logging.disable(logging.INFO)
    engine = get_engine()
    if not engine.url.database or not engine.url.database.endswith("_test"):
        raise ValueError(
            "Refusing benchmark against anything other than a *_test database"
        )
    settings = Settings(_env_file=None, DATABASE_URL=os.environ["DATABASE_URL"])
    attempt, repo = uuid.uuid4(), str(uuid.uuid4())
    factory = get_sessionmaker()
    sampler = Sampler()
    sampler.emit(
        {
            "kind": "environment",
            "runtime_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                text=True,
            ).strip(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pid": os.getpid(),
            "files": args.files,
            "payload_chars": args.payload_chars,
            "embedder": "deterministic-1024d-stub",
            "fixture": "generated-python-v1",
            "page_limit": settings.INGESTION_NODE_PAGE_SIZE,
            "artifact_limit_bytes": settings.INGESTION_MAX_ARTIFACT_BYTES,
            "buffer_count_limit": settings.INGESTION_EMBED_BATCH_SIZE,
            "buffer_byte_limit": settings.INGESTION_EMBED_MAX_BYTES,
            "cgroup_membership": Path("/proc/self/cgroup").read_text(),
            "cgroup_note": (
                "Mount-root counters may include other processes; RSS is per PID"
            ),
        }
    )
    sampler.sample()
    sampler.thread.start()
    store = HttpVectorStore(args.vector_url)

    class Embedder:
        def embed(self, chunks):
            vectors = [
                [float((i + len(chunk.content)) % 257) / 257 for i in range(1024)]
                for chunk in chunks
            ]
            sampler.sample()  # Observe live Python float vectors before persistence.
            return vectors

    pipeline = IngestionPipeline(
        validator=None, embedder=Embedder(), vector_store=store
    )
    latest = {}
    observed = {"max_page_nodes": 0, "max_page_bytes": 0, "max_artifact_bytes": 0}

    class ObservedPersistence(CodebaseGraphPersistence):
        def iter_artifact_pages(self, *args, **kwargs):
            for page in super().iter_artifact_pages(*args, **kwargs):
                sizes = [len((row.text or "").encode("utf-8")) for row in page]
                observed["max_page_nodes"] = max(observed["max_page_nodes"], len(page))
                observed["max_page_bytes"] = max(observed["max_page_bytes"], sum(sizes))
                observed["max_artifact_bytes"] = max(
                    observed["max_artifact_bytes"],
                    max(sizes, default=0),
                )
                sampler.emit({"kind": "page", **observed})
                yield page
                del page

    try:
        with tempfile.TemporaryDirectory(prefix="rag-memory-fixture-") as directory:
            sampler.set_stage("fixture")
            for index in range(args.files):
                (Path(directory) / f"m{index:06d}.py").write_text(
                    "def sample():\n    value = '"
                    + "x" * args.payload_chars
                    + "'\n    return value\n",
                    encoding="utf-8",
                )
            with factory() as session:
                manager = StatusManager(session)
                manager.create_request(
                    ingestion_id=attempt, source_type="repo", metadata={}
                )
                manager.mark_running(attempt)
                persistence = ObservedPersistence(session)
                stats = _build_and_persist_graph(
                    directory,
                    repo,
                    attempt,
                    persistence,
                    sampler.set_stage,
                )

                def report(progress):
                    if sampler.stage != progress["stage"]:
                        sampler.set_stage(progress["stage"])
                    latest.update(progress)
                    manager.update_embed_progress(attempt, progress)
                    sampler.emit({"kind": "progress", **progress})

                chunks, skipped = _embed_repo_artifacts(
                    pipeline,
                    persistence,
                    repo,
                    str(attempt),
                    stats["nodes"],
                    "mock",
                    settings,
                    report,
                )
                manager.mark_completed(attempt)
                sampler.set_stage("completed")
            with factory() as observer:
                persisted = observer.execute(
                    text("""
                    SELECT count(*) FROM ingestion_service.vector_chunks
                    WHERE ingestion_id = :attempt
                """),
                    {"attempt": str(attempt)},
                ).scalar()
            assert persisted == chunks and skipped == 0
            sampler.emit(
                {
                    "kind": "summary",
                    "terminal": "completed",
                    "nodes": stats["nodes"],
                    "chunks": chunks,
                    "persisted": persisted,
                    "progress": latest,
                    "observed": observed,
                    "baseline_rss_bytes": sampler.baselines,
                    "peak_rss_bytes": sampler.peaks,
                    "embedding_incremental_rss_bytes": max(
                        0,
                        sampler.peaks["embedding"] - sampler.baselines["embedding"],
                    ),
                    "elapsed_seconds": time.monotonic() - sampler.started,
                }
            )
    finally:
        sampler.set_stage("cleanup")
        try:
            store.delete_by_ingestion_id(str(attempt))
            with factory() as session:
                session.query(DocumentNode).filter_by(repo_id=repo).delete(
                    synchronize_session=False,
                )
                session.query(IngestionRequest).filter_by(ingestion_id=attempt).delete()
                session.commit()
        finally:
            sampler.stop.set()
            sampler.thread.join(timeout=2)


if __name__ == "__main__":
    main()
