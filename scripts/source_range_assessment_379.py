"""Owner-authorized #379 read-only PostgreSQL range diagnostic; no endpoints.

Use --dsn-env NAME or --existing-connection to reuse db_inspect's existing
connection settings with the Linux host from REMOTE_OLLAMA_BASE_URL in .env.
Never print addresses, credentials or source text. Writes local evidence only.
No server cache reset, fixture creation, extensions, DDL or DML are performed.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import runpy
import statistics
import subprocess
import time
import tracemalloc
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
SOURCE_TYPES = [
    "python source", "typescript source", "javascript source",
    "rust source", "java source",
]
CONNECTION_OPTIONS = (
    "-c default_transaction_read_only=on -c statement_timeout=5000 "
    "-c lock_timeout=1000 -c idle_in_transaction_session_timeout=30000 "
    "-c application_name=foundry_ag0_readonly_assessment"
)
IDENTITY = """
FROM ingestion_service.document_nodes
WHERE repo_id=%(repo_id)s AND ingestion_id=%(ingestion_id)s
  AND canonical_id=%(canonical_id)s
"""
SLICE = "SELECT substring(text FROM %(offset)s FOR %(count)s) AS text " + IDENTITY
FULL = "SELECT text " + IDENTITY
# Deliberately rejected comparator: constructs a full line array on the server.
ARRAY = """
WITH source AS MATERIALIZED (
 SELECT string_to_array(text, E'\\n') AS lines
""" + IDENTITY + """
)
SELECT array_to_string(lines[%(start)s:%(end)s], E'\\n')
 || CASE WHEN %(end)s < cardinality(lines) THEN E'\\n' ELSE '' END AS text
FROM source
"""


def lf_lines(text):
    """Split only on LF, preserving exactly the stored characters."""
    if not text:
        return []
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def window_range(fetch, start, end, window=32768, cap=131072):
    """Diagnostic bounded-transfer scanner; not product implementation."""
    offset, line, size, queries, transferred = 1, 1, 0, 0, 0
    output = []
    deadline = time.monotonic() + 5
    while line <= end:
        if time.monotonic() > deadline:
            raise TimeoutError("logical read exceeded five seconds")
        block = fetch(offset, window)
        queries += 1
        transferred += len(block.encode("utf-8"))
        if not block:
            break
        pos = 0
        while pos < len(block) and line <= end:
            newline = block.find("\n", pos)
            stop = len(block) if newline < 0 else newline + 1
            if line >= start:
                piece = block[pos:stop]
                size += len(piece.encode("utf-8"))
                if size > cap:
                    raise ValueError("response cap exceeded")
                output.append(piece)
            if newline >= 0:
                line += 1
            pos = stop
        offset += len(block)
        if len(block) < window:
            break
    return "".join(output), {"queries": queries, "transferred_utf8_bytes": transferred}


def remote_host():
    env = dict(
        line.split("=", 1)
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    match = re.match(r"https?://([^:/]+)", env["REMOTE_OLLAMA_BASE_URL"].strip())
    if not match:
        raise ValueError("missing remote host configuration")
    return match.group(1)


def connect(args) -> psycopg.Connection[dict[str, Any]]:
    if args.dsn_env:
        conn = psycopg.Connection[dict[str, Any]].connect(
            os.environ[args.dsn_env], options=CONNECTION_OPTIONS,
            connect_timeout=10, row_factory=dict_row,
        )
    else:
        config = runpy.run_path(str(ROOT / "scripts/db_inspect.py"))["CONN_DEFAULTS"]
        config = dict(config, host=remote_host())
        conn = psycopg.Connection[dict[str, Any]].connect(
            **config, options=CONNECTION_OPTIONS, connect_timeout=10,
            row_factory=dict_row,
        )
    conn.read_only = True
    conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
    return conn


def explain(cur, sql, params):
    cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, TIMING OFF) " + sql, params)
    return cur.fetchone()["QUERY PLAN"][0]


def memory_snapshot(cur):
    try:
        # Savepoint keeps a privilege failure from aborting the read transaction.
        with cur.connection.transaction():
            cur.execute("SELECT sum(total_bytes) AS allocated, sum(used_bytes) AS used "
                        "FROM pg_backend_memory_contexts")
            return cur.fetchone()
    except psycopg.errors.InsufficientPrivilege:
        return {"unavailable": "insufficient privilege"}


def measured(call):
    tracemalloc.start()
    started = time.perf_counter()
    try:
        text, metadata = call()
        elapsed = (time.perf_counter() - started) * 1000
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return text, dict(metadata, client_ms=elapsed, python_traced_peak_bytes=peak)


def fetch_text(cur, sql, params):
    cur.execute(sql, params)
    return cur.fetchone()["text"]


def generation(cur, repo_id):
    cur.execute("""
        SELECT DISTINCT n.ingestion_id::text, i.status, i.commit_sha
        FROM ingestion_service.document_nodes n
        JOIN ingestion_service.ingestion_requests i USING (ingestion_id)
        WHERE n.repo_id=%s
    """, (repo_id,))
    return cur.fetchall()


def benchmark_file(args, item):
    result: dict[str, Any] = dict(item, regions=[])
    with connect(args) as conn, conn.cursor() as cur:
        owner = generation(cur, item["repo_id"])
        assert len(owner) == 1 and owner[0]["status"] == "completed"
        assert owner[0]["ingestion_id"] == str(item["ingestion_id"])
        result["generation_before"] = owner
        p = dict(item, offset=1, count=32768)
        # First observed text access. Never call this a cold-cache measurement.
        result["first_observed_plan"] = explain(cur, SLICE, p)
        full = fetch_text(cur, FULL, p)  # correctness oracle, not a timed range
        lines = lf_lines(full)
        result.update(characters=len(full), line_count=len(lines),
                      stored_text_sha256=hashlib.sha256(full.encode()).hexdigest())
        if item["canonical_id"].endswith("/codebase_utils.py"):
            tree = ast.parse(full)
            result["stored_python_inventory"] = [
                {"name": n.name, "line": n.lineno,
                 "async": isinstance(n, ast.AsyncFunctionDef)}
                for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
        result["backend_memory_before"] = memory_snapshot(cur)
        for label, start in (
            ("early", 1),
            ("middle", max(1, len(lines) // 2 - 49)),
            ("late", max(1, len(lines) - 99)),
        ):
            end = min(len(lines), start + 99)
            expected = "".join(lines[start - 1:end])
            params = dict(p, start=start, end=end,
                          offset=len("".join(lines[:start - 1])) + 1,
                          count=len(expected))
            region = {"label": label, "start_line": start, "end_line": end,
                      "returned_bytes": len(expected.encode()), "methods": {}}
            for method in ("known_offset", "window_scan", "full_array", "full_fetch"):
                samples = []

                def operation():
                    if method == "window_scan":
                        return window_range(
                            lambda offset, count: fetch_text(
                                cur, SLICE, dict(p, offset=offset, count=count)),
                            start, end,
                        )
                    sql = {"known_offset": SLICE, "full_array": ARRAY,
                           "full_fetch": FULL}[method]
                    text = fetch_text(cur, sql, params)
                    transferred = len(text.encode())
                    if method == "full_fetch":
                        text = "".join(lf_lines(text)[start - 1:end])
                    return text, {"queries": 1, "transferred_utf8_bytes": transferred}

                for _ in range(args.repeats):
                    actual, stats = measured(operation)
                    assert actual == expected, (item["canonical_id"], label, method)
                    samples.append(stats)
                row = {"samples": samples,
                       "median_client_ms": statistics.median(
                           s["client_ms"] for s in samples)}
                if method != "window_scan":
                    row["plan"] = explain(
                        cur, {"known_offset": SLICE, "full_array": ARRAY,
                              "full_fetch": FULL}[method], params,
                    )
                else:
                    # One window at the target, not the whole logical scanner.
                    row["target_window_plan"] = explain(
                        cur, SLICE, dict(params, count=32768))
                region["methods"][method] = row
            result["regions"].append(region)
        result["backend_memory_after"] = memory_snapshot(cur)
        assert generation(cur, item["repo_id"]) == owner
    # New snapshot detects a rebuild committed while benchmarking this file.
    with connect(args) as conn, conn.cursor() as cur:
        result["generation_after_fresh_snapshot"] = generation(cur, item["repo_id"])
        result["generation_unchanged"] = (
            result["generation_after_fresh_snapshot"] == owner
        )
    return result


def inventory(args):
    with connect(args) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT version(), current_setting('transaction_read_only') AS read_only,
                   current_setting('server_encoding') AS encoding,
                   current_setting('default_toast_compression') AS toast_compression,
                   current_setting('track_io_timing') AS track_io_timing,
                   current_setting('shared_buffers') AS shared_buffers,
                   current_setting('statement_timeout') AS statement_timeout,
                   current_setting('transaction_isolation') AS isolation
        """)
        environment = cur.fetchone()
        cur.execute("""
            WITH owners AS (
              SELECT repo_id, min(ingestion_id::text) AS ingestion_id
              FROM ingestion_service.document_nodes GROUP BY repo_id
              HAVING count(DISTINCT ingestion_id)=1
            )
            SELECT n.repo_id, n.ingestion_id::text, n.canonical_id, n.doc_type,
                   octet_length(n.text) AS source_bytes,
                   pg_column_size(n.text) AS stored_bytes,
                   pg_column_compression(n.text) AS compression,
                   i.commit_sha
            FROM ingestion_service.document_nodes n
            JOIN owners o ON o.repo_id=n.repo_id
                         AND o.ingestion_id=n.ingestion_id::text
            JOIN ingestion_service.ingestion_requests i
              ON i.ingestion_id=n.ingestion_id
            WHERE n.canonical_id=n.relative_path AND n.doc_type=ANY(%s)
              AND n.text IS NOT NULL AND i.status='completed'
        """, (SOURCE_TYPES,))
        files = cur.fetchall()
    return environment, files


def runtime_versions():
    found = {}
    try:
        host = remote_host()
    except (KeyError, ValueError, FileNotFoundError):
        return {"unavailable": "no HTTP host configuration"}
    for service, port in (("ingestion", 8001), ("orchestrator", 8004)):
        try:
            with urlopen(f"http://{host}:{port}/version", timeout=3) as response:
                data = json.load(response)
                found[service] = {k: data.get(k) for k in
                                  ("git_sha", "build_date", "release_version")}
        except Exception as exc:
            found[service] = {"unavailable": type(exc).__name__}
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    auth = parser.add_mutually_exclusive_group(required=True)
    auth.add_argument("--dsn-env")
    auth.add_argument("--existing-connection", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5, choices=range(1, 11))
    args = parser.parse_args()
    environment, files = inventory(args)
    if not files:
        raise RuntimeError("No ready source files available")
    selected = [max(files, key=lambda f: f["source_bytes"])]
    for target in (8192, 65536):
        selected.append(min(files, key=lambda f: abs(f["source_bytes"] - target)))
    uncompressed = [f for f in files if f["compression"] is None]
    if uncompressed:
        selected.append(max(uncompressed, key=lambda f: f["source_bytes"]))
    selected.extend(
        f for f in files if f["canonical_id"].endswith("/codebase_utils.py")
    )
    unique = {(f["repo_id"], f["canonical_id"]): f for f in selected}
    result = {
        "issue": 379, "started_utc": datetime.now(timezone.utc).isoformat(),
        "environment": environment, "client": platform.platform(),
        "python": platform.python_version(), "psycopg": psycopg.__version__,
        "local_git_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "runtime_versions": runtime_versions(),
        "inventory": {"ready_files": len(files),
                      "max_bytes": max(f["source_bytes"] for f in files),
                      "over_4_mib": sum(f["source_bytes"] > 4194304 for f in files),
                      "compression_counts": dict(Counter(
                          str(f["compression"]) for f in files))},
        "cache_policy": "first-observed plan then warmed correctness oracle; "
                        "no true cold-cache run, no cache reset or restart",
        "selection": "largest ready file; nearest 8KiB and 64KiB; largest "
                     "uncompressed file; all codebase_utils.py module matches",
        "limitations": ["no backend peak-RSS measurement",
                        "Python tracing excludes native libpq/driver allocations",
                        "backend memory view is post-query, not executor peak",
                        "inventory and correctness checks can warm caches"],
        "sql": {"slice": SLICE, "full_array_comparator": ARRAY, "full": FULL},
        "files": [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for item in unique.values():
        print(json.dumps({"benchmarking": item["canonical_id"],
                          "source_bytes": item["source_bytes"]}), flush=True)
        result["files"].append(benchmark_file(args, item))
        args.out.write_text(json.dumps(result, indent=2, default=str) + "\n")
    result["finished_utc"] = datetime.now(timezone.utc).isoformat()
    args.out.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps({"complete": True, "files": len(result["files"])}))


if __name__ == "__main__":
    main()
