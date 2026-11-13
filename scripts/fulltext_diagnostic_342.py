"""Issue #342: read-only source full-text discovery diagnostic (owner-authorized).

Ranks the generation's stored chunks for the unchanged Step 0 question by
PostgreSQL full-text search, with terms derived automatically from the
question (every English lexeme of it, OR-combined; nothing hand-picked), and
compares with exact vector ranking and their RRF fusion, in three scopes
(all, source-only, source + path-role filter).

Only SELECT and EXPLAIN (without ANALYZE) are issued, on a read-only
connection. Nothing is written; the generation is checked unchanged before
and after. The ground truth in discovery_diagnostic_342 (TARGETS, HOPS) is
used only to score the rankings afterwards.

    python scripts/fulltext_diagnostic_342.py STEP0.json CANDIDATES_RUN3.json \
        --out RAW/2026-11-12-342-fulltext-discovery.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
import discovery_diagnostic_342 as dd  # noqa: E402

RRF_K = 60
FUSION_POOL = 100  # chunks per channel entering fusion (as in the 11-12 study)
CUTOFFS = (20, 50, 100)
CODE_TARGETS = {k: v for k, v in dd.TARGETS.items() if not v.startswith("route:")}

TERMS_SQL = """
SELECT string_agg(quote_literal(l), ' | ' ORDER BY l)
FROM unnest(tsvector_to_array(to_tsvector('english', %(q)s))) AS l
"""

FTS_SQL = """
SELECT source_metadata->>'canonical_id' AS cid, chunk_index, doc_type,
       ts_rank_cd(
         setweight(to_tsvector('english', replace(coalesce(
           source_metadata->>'canonical_id', ''), '_', ' ')), 'A')
         || setweight(to_tsvector('english', coalesce(chunk_text, '')), 'B'),
         %(tsq)s::tsquery) AS score
FROM ingestion_service.vector_chunks
WHERE repo_id = %(repo)s AND ingestion_id = %(gen)s
"""

VECTOR_SQL = """
SELECT source_metadata->>'canonical_id' AS cid, chunk_index, doc_type,
       1 - (vector <=> %(qvec)s::vector) AS score
FROM ingestion_service.vector_chunks
WHERE repo_id = %(repo)s AND ingestion_id = %(gen)s
"""

TEXT_SQL = """
SELECT source_metadata->>'canonical_id', chunk_index, chunk_text
FROM ingestion_service.vector_chunks
WHERE repo_id = %(repo)s AND ingestion_id = %(gen)s
  AND source_metadata->>'canonical_id' = ANY(%(cids)s)
"""

COUNT_SQL = """
SELECT ingestion_id::text, count(*) FROM ingestion_service.vector_chunks
WHERE repo_id = %(repo)s GROUP BY ingestion_id ORDER BY ingestion_id
"""


def in_scope(row: tuple, scope: str) -> bool:
    cid, _, doc_type = row[:3]
    if scope == "all":
        return True
    if not str(doc_type or "").endswith(" source"):
        return False
    return scope == "source" or not dd.PATH_ROLE_EXCLUDE.search(str(cid).split("#")[0])


def ranked(rows: list[tuple], scope: str, positive_only: bool) -> list[tuple]:
    """Rows in scope, score descending, ties by canonical id then chunk."""
    keep = [r for r in rows if in_scope(r, scope) and (r[3] > 0 or not positive_only)]
    return sorted(keep, key=lambda r: (-float(r[3]), str(r[0]), r[1]))


def artifact_ranks(chunks: list[tuple]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in chunks:
        out.setdefault(r[0], len(out) + 1)
    return out


def chunk_ranks(chunks: list[tuple]) -> dict[tuple[str, int], int]:
    return {(r[0], r[1]): i for i, r in enumerate(chunks, 1)}


def fuse(channels: list[list[tuple]]) -> list[tuple[str, float]]:
    score: dict[str, float] = {}
    for chunks in channels:
        for cid, rank in artifact_ranks(chunks[:FUSION_POOL]).items():
            score[cid] = score.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))


def recall(ranks: dict[str, int | None]) -> dict[str, float]:
    n = len(CODE_TARGETS)
    return {
        f"@{k}": round(sum(1 for r in ranks.values() if r and r <= k) / n, 3)
        for k in CUTOFFS
    }


def channel_report(art: dict[str, int], top: list[str]) -> dict:
    ranks = {k: art.get(cid) for k, cid in CODE_TARGETS.items()}
    return {"target_artifact_ranks": ranks, "recall": recall(ranks), "top20": top[:20]}


def witness_support(texts: dict, channels: dict[str, list[tuple]]) -> list[dict]:
    """For each source-witnessed hop: the caller chunk(s) whose stored text
    contains the witness, and that chunk's best rank in each channel."""
    out = []
    for hid, frm, to, kind, pattern in dd.HOPS:
        if not pattern:
            continue
        cid = dd.TARGETS[frm]
        chunks = sorted(
            idx for (c, idx), t in texts.items() if c == cid and re.search(pattern, t)
        )
        ranks = {}
        for name, rows in channels.items():
            pos = chunk_ranks(rows)
            found = [pos[(cid, i)] for i in chunks if (cid, i) in pos]
            ranks[name] = min(found) if found else None
        out.append(
            {
                "hop": hid,
                "from": frm,
                "to": to or "(outside repository)",
                "kind": kind,
                "witness_chunks": chunks,
                "best_witness_chunk_rank": ranks,
            }
        )
    return out


def connect():
    host = re.match(r"https?://([^:/]+)", dd.host_from_env()).group(1)
    conn = psycopg.connect(
        host=host,
        port=5434,
        user="ingestion_user",
        password="ingestion_pass",
        dbname="ingestion_db",
        connect_timeout=10,
    )
    conn.read_only = True
    return conn


def run(args) -> dict:
    step0 = json.loads(args.step0.read_text(encoding="utf-8"))
    cand = json.loads(args.candidates.read_text(encoding="utf-8"))
    query = step0["application_input"]["messages"][1]["content"]
    query = query.rsplit("Question:\n", 1)[1].strip()
    p = {"repo": step0["repo_id"], "gen": step0["generation_id"], "q": query}
    p["qvec"] = "[" + ",".join(map(str, cand["query_vector"])) + "]"
    with connect() as conn, conn.cursor() as cur:
        cur.execute(COUNT_SQL, p)
        counts_before = cur.fetchall()
        cur.execute(TERMS_SQL, p)
        p["tsq"] = cur.fetchone()[0]
        cur.execute("EXPLAIN " + FTS_SQL, p)
        plan = [r[0] for r in cur.fetchall()]
        cur.execute(FTS_SQL, p)
        fts_rows = cur.fetchall()
        cur.execute(VECTOR_SQL, p)
        vec_rows = cur.fetchall()
        cur.execute(TEXT_SQL, {**p, "cids": list(dd.TARGETS.values())})
        texts = {(c, i): t for c, i, t in cur.fetchall()}
        cur.execute(COUNT_SQL, p)
        counts_after = cur.fetchall()
        conn.rollback()

    scopes = {}
    support_channels = {}
    for scope in ("all", "source", "path_role"):
        fts = ranked(fts_rows, scope, positive_only=True)
        vec = ranked(vec_rows, scope, positive_only=False)
        fused = fuse([vec, fts])
        fused_art = {cid: i for i, (cid, _) in enumerate(fused, 1)}
        scopes[scope] = {
            "chunks_in_scope": sum(1 for r in vec_rows if in_scope(r, scope)),
            "fts_matching_chunks": len(fts),
            "fulltext": channel_report(artifact_ranks(fts), list(artifact_ranks(fts))),
            "vector": channel_report(artifact_ranks(vec), list(artifact_ranks(vec))),
            "rrf_vector_fulltext": channel_report(fused_art, [c for c, _ in fused]),
        }
        support_channels[f"fulltext/{scope}"] = fts
        support_channels[f"vector/{scope}"] = vec

    return {
        "schema": "fulltext_diagnostic_342.v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "scope": "read-only connection; SELECT and EXPLAIN (no ANALYZE) only",
        "git_head": os.popen("git rev-parse HEAD").read().strip(),
        "repo_id": p["repo"],
        "generation_id": p["gen"],
        "chunk_counts_before": counts_before,
        "chunk_counts_after": counts_after,
        "generation_unchanged": counts_before == counts_after,
        "query": query,
        "term_policy": "every lexeme of to_tsvector('english', question), OR-combined",
        "tsquery": p["tsq"],
        "fts_sql": FTS_SQL.strip(),
        "explain_fts": plan,
        "fusion": {"method": "RRF", "k": RRF_K, "pool_chunks_per_channel": FUSION_POOL},
        "code_targets": CODE_TARGETS,
        "scopes": scopes,
        "witness_support": witness_support(texts, support_channels),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("step0", type=Path)
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    data = run(args)
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({"generation_unchanged": data["generation_unchanged"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
