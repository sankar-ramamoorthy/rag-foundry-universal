"""Phase 1 exit benchmark (roadmap 07: "2k-file repo ingests fast,
vector search uses index").

Measures each ingestion stage at 2k-file / ~50k-symbol scale against the
docker-compose.test.yml Postgres, plus real-Ollama embedding throughput
(sampled) and index-backed vector-search latency:

  1. synthetic repo generation           (2000 files, 20 funcs + 1 class
                                          with 5 methods per file)
  2. RepoGraphBuilder.build()            (WP-S1: target < 60 s)
  3. persist_graph()                     (WP-S3: 50k nodes + edges < 30 s)
  4. canonical_id -> document_id map     (F-08: single query)
  5. chunking of every artifact          (F-08 batch stage, CPU only)
  6. Ollama embed throughput, 50 chunks  (hardware-bound; projected total
                                          reported, not waited on)
  7. similarity-search latency p50/p95   (F-10: HNSW + ef_search, 5000
                                          synthetic rows, filtered query)

Usage (from ingestion_service/, root venv, test DB up + migrated):
  DATABASE_URL=postgresql://ingestion_user:ingestion_pass@localhost:5433/ingestion_test \
    ../.venv/Scripts/python.exe ../DOCS/test_results/phase1_benchmark.py
"""
import json
import os
import random
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, "..")
sys.path.insert(0, ".")

N_FILES = 2000
N_FUNCS = 20  # + 1 class with 5 methods per file → ~54k artifacts


def write_synthetic(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for i in range(N_FILES):
        lines = [f"import mod{(i + 1) % N_FILES}\n\n"]
        for j in range(N_FUNCS):
            lines.append(
                f"def func_{i}_{j}(a, b):\n"
                f"    x = a + b\n"
                f"    return func_{i}_{(j + 1) % N_FUNCS}(x, b)\n\n"
            )
        lines.append(f"class Klass{i}:\n")
        for j in range(5):
            lines.append(
                f"    def method_{j}(self):\n"
                f"        return func_{i}_{j}(1, 2)\n\n"
            )
        (root / f"mod{i}.py").write_text("".join(lines), encoding="utf-8")


def main() -> None:
    import src.core.models  # noqa: F401  (register FK metadata)
    from src.core.codebase.repo_graph_builder import RepoGraphBuilder
    from src.core.codebase.codebase_persistence import CodebaseGraphPersistence
    from src.core.database_session import get_sessionmaker
    from src.core.status_manager import StatusManager
    from src.core.pipeline import IngestionPipeline

    out: dict = {"n_files": N_FILES}
    ingestion_id = uuid.uuid4()
    repo_id = str(uuid.uuid4())

    root = Path(tempfile.mkdtemp()) / "phase1_bench_repo"
    t0 = time.perf_counter()
    write_synthetic(root)
    out["generate_s"] = round(time.perf_counter() - t0, 2)

    # --- 2. graph build (WP-S1) ---
    t0 = time.perf_counter()
    graph = RepoGraphBuilder(
        repo_root=root, ingestion_id=str(ingestion_id)
    ).build()
    out["graph_build_s"] = round(time.perf_counter() - t0, 2)
    nodes = graph.all_entities()
    out["n_artifacts"] = len(nodes)
    out["n_relationships"] = len(graph.relationships)

    # --- 3. atomic bulk persist (WP-S3) ---
    Session = get_sessionmaker()
    session = Session()
    StatusManager(session).create_request(
        ingestion_id=ingestion_id, source_type="repo", metadata={}
    )
    for node in nodes:
        node["ingestion_id"] = str(ingestion_id)
    persistence = CodebaseGraphPersistence(session=session)
    t0 = time.perf_counter()
    stats = persistence.persist_graph(
        repo_id=repo_id, nodes=nodes, relationships=graph.relationships
    )
    out["persist_graph_s"] = round(time.perf_counter() - t0, 2)
    out["persisted"] = stats

    # --- 4. canonical map (F-08) ---
    t0 = time.perf_counter()
    canonical_map = persistence.get_canonical_id_map(repo_id)
    out["canonical_map_s"] = round(time.perf_counter() - t0, 2)
    assert len(canonical_map) == len(nodes)

    # --- 5. chunking stage (F-08, CPU only) ---
    class _NoOp:
        def validate(self, text):
            return None

    pipeline = IngestionPipeline(
        validator=_NoOp(), embedder=None, vector_store=None
    )
    chunks = []
    t0 = time.perf_counter()
    for node in nodes:
        text = node.get("text", "")
        if text.strip():
            chunks.extend(pipeline._chunk(text, "code", "ollama"))
    out["chunking_s"] = round(time.perf_counter() - t0, 2)
    out["n_chunks"] = len(chunks)

    # --- 6. embedding throughput probe (hardware-bound) ---
    import requests

    ollama = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model = os.environ.get("OLLAMA_EMBED_MODEL", "mxbai-embed-large:latest")
    sample = [c.content[:800] for c in chunks[:50]]
    requests.post(  # warmup / model load
        f"{ollama}/api/embed", json={"model": model, "input": sample[:2]},
        timeout=300,
    )
    t0 = time.perf_counter()
    r = requests.post(
        f"{ollama}/api/embed", json={"model": model, "input": sample},
        timeout=600,
    )
    dt = time.perf_counter() - t0
    r.raise_for_status()
    rate = len(sample) / dt
    out["embed_chunks_per_s"] = round(rate, 1)
    out["embed_projected_total_s"] = round(len(chunks) / rate)

    # --- 7. search latency with HNSW (F-10) ---
    import psycopg

    dsn = os.environ["DATABASE_URL"]
    rng = random.Random(1)
    n_rows = 5000
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            with cur.copy(
                "COPY ingestion_service.vector_chunks "
                "(vector, ingestion_id, chunk_id, chunk_index, "
                "chunk_strategy, chunk_text, source_metadata, provider) "
                "FROM STDIN"
            ) as copy:
                for i in range(n_rows):
                    vec = "[" + ",".join(
                        f"{rng.uniform(-1, 1):.4f}" for _ in range(1024)
                    ) + "]"
                    copy.write_row((
                        vec, str(ingestion_id), f"bench-{i}", i, "bench",
                        f"chunk {i}",
                        json.dumps({"doc_type": "code", "repo_id": repo_id}),
                        "bench",
                    ))
            cur.execute("ANALYZE ingestion_service.vector_chunks")

        latencies = []
        for _ in range(50):
            qvec = "[" + ",".join(
                f"{rng.uniform(-1, 1):.4f}" for _ in range(1024)
            ) + "]"
            t0 = time.perf_counter()
            with conn.cursor() as cur:
                cur.execute("SET LOCAL hnsw.ef_search = 100")
                cur.execute(
                    "SELECT chunk_id, 1 - (vector <=> %s::vector) AS score "
                    "FROM ingestion_service.vector_chunks "
                    "WHERE source_metadata->>'doc_type' = 'code' "
                    "ORDER BY vector <=> %s::vector LIMIT 10",
                    (qvec, qvec),
                )
                cur.fetchall()
            conn.commit()
            latencies.append((time.perf_counter() - t0) * 1000)
        out["search_rows"] = n_rows
        out["search_p50_ms"] = round(statistics.median(latencies), 1)
        out["search_p95_ms"] = round(
            statistics.quantiles(latencies, n=20)[18], 1
        )

        with conn.cursor() as cur:
            cur.execute(
                "EXPLAIN (FORMAT JSON) SELECT chunk_id "
                "FROM ingestion_service.vector_chunks "
                "ORDER BY vector <=> %s::vector LIMIT 10",
                (qvec,),
            )
            plan = json.dumps(cur.fetchone()[0])
            out["search_uses_hnsw"] = "ix_vector_chunks_hnsw" in plan

        # cleanup benchmark rows
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM ingestion_service.vector_chunks "
                "WHERE ingestion_id = %s",
                (str(ingestion_id),),
            )
        conn.commit()

    persistence.delete_repo_nodes(repo_id)
    session.close()

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
