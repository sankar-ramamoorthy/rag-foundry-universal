"""Opt-in benchmark for GET /v1/graph/repos/{repo_id} (issues #270, #273).

Generates a synthetic repo graph in a TEST database, starts the real
ingestion_service app under one uvicorn process, and for each concurrency level
measures export latency, the slowest concurrent /version probe, peak process
memory and the canonical response hash. Not collected by pytest, not run in CI.

    BENCH_DATABASE_URL=postgresql://USER:PASS@HOST:PORT/ingestion_test \\
        python scripts/graph_export_benchmark.py --nodes 15000 --output out.json

Needs a migrated database (alembic upgrade head) and the root virtualenv.
Use --repo-root to benchmark another checkout (e.g. a git worktree of a branch)
with identical flags, and --expect-hash to assert the response is unchanged.
The response hash depends only on --nodes and --edges-per-node, not on text size.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import psycopg2

# A clearly synthetic id; the only repo this script ever writes or deletes.
REPO_ID = "00000000-0000-4000-8000-000000000273"
INGESTION_ID = "00000000-0000-4000-8000-000000000274"
DEFAULT_ROOT = Path(__file__).resolve().parents[1]


# ----------------------------------------------------------------- pure helpers


def check_database_url(url: str, force: bool = False) -> str:
    """Return the database name; refuse anything that doesn't look disposable."""
    name = urlparse(url).path.lstrip("/")
    if not name:
        raise ValueError("database URL has no database name")
    if not force and not any(tag in name.lower() for tag in ("test", "bench")):
        raise ValueError(
            f"database {name!r} does not look like a test/bench database; "
            "the benchmark writes fixture rows. Use a test database or --force-db."
        )
    return name


def fixture_statements(nodes: int, mean_text_bytes: int, edges: int) -> list[str]:
    """SQL that (re)creates the synthetic repo; deletes only REPO_ID's rows."""
    if nodes < 1 or edges < 0 or mean_text_bytes < 40:
        raise ValueError("need nodes >= 1, edges >= 0, mean_text_bytes >= 40")
    scale = mean_text_bytes / 0.775  # skewed length below has mean 0.775 * scale
    return [
        "SET search_path = ingestion_service, public",
        # Relationships first, by their indexed repo_id: the FK cascade from
        # document_nodes scans document_relationships.to_document_id (no index).
        f"DELETE FROM document_relationships WHERE repo_id = '{REPO_ID}'",
        f"DELETE FROM document_nodes WHERE repo_id = '{REPO_ID}'",
        f"DELETE FROM ingestion_requests WHERE ingestion_id = '{INGESTION_ID}'",
        "INSERT INTO ingestion_requests"
        " (ingestion_id, source_type, repo_id, status, finished_at)"
        f" VALUES ('{INGESTION_ID}', 'repo', '{REPO_ID}', 'completed', now())",
        "INSERT INTO document_nodes (document_id, repo_id, canonical_id,"
        " relative_path, symbol_path, title, summary, source, ingestion_id,"
        " doc_type, text, content_hash, provenance)"
        " SELECT md5('" + REPO_ID + "n' || i)::uuid, '" + REPO_ID + "',"
        " 'pkg/mod' || (i / 20) || '.py#sym' || i, 'pkg/mod' || (i / 20) || '.py',"
        " 'sym' || i, 'sym' || i, 'summary ' || i, 'codebase', '" + INGESTION_ID + "',"
        " 'function', left((SELECT string_agg(md5(i::text || k::text), '')"
        " FROM generate_series(1, 1 + (len / 32)) k), len), md5(i::text),"
        ' \'{"authority":"code","subject":"synthetic"}\'::json'
        " FROM (SELECT i, GREATEST(40, floor("
        f"{scale} * (0.1 + 2.7 * power(random(), 3))))::int AS len"
        f" FROM generate_series(1, {nodes}) i) s",
        "INSERT INTO document_relationships (from_document_id, to_document_id,"
        " relation_type, relationship_metadata, repo_id)"
        " SELECT md5('" + REPO_ID + "n' || i)::uuid,"
        f" md5('{REPO_ID}n' || (((i * 7919 + k * 104729) % {nodes}) + 1))::uuid,"
        " (ARRAY['CALLS','DEFINES','IMPORTS','INHERITS'])[1 + (k % 4)],"
        " '{\"confidence\":0.9}'::jsonb, '" + REPO_ID + "'"
        f" FROM generate_series(1, {nodes}) i, generate_series(1, {edges}) k"
        " ON CONFLICT DO NOTHING",
        "ANALYZE document_nodes",
        "ANALYZE document_relationships",
    ]


def canonical_hash(body: bytes) -> str:
    """Hash of the response independent of node/edge ordering."""
    data = json.loads(body)
    data["nodes"].sort(key=lambda n: n["canonical_id"])
    for edges in data["relationships"].values():
        edges.sort(key=lambda e: (e["to_canonical_id"], e["relation_type"]))
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def summarize(values: list[float]) -> dict:
    return {
        "min": round(min(values), 2),
        "median": round(statistics.median(values), 2),
        "max": round(max(values), 2),
    }


def projected_peak_mb(idle_mb: float, per_export_mb: float, level: int,
                      headroom: float) -> float:
    return idle_mb + level * per_export_mb * headroom


# ------------------------------------------------------------- platform helpers


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_uint32), ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class _ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_uint32), ("cntUsage", ctypes.c_uint32),
        ("pid", ctypes.c_uint32), ("heap", ctypes.c_size_t),
        ("module", ctypes.c_uint32), ("threads", ctypes.c_uint32),
        ("ppid", ctypes.c_uint32), ("priority", ctypes.c_long),
        ("flags", ctypes.c_uint32), ("exe", ctypes.c_wchar * 260),
    ]


def _windows_process_tree(pid: int) -> list[int]:
    """pid plus its descendants. A venv's python.exe is a launcher that spawns
    the real interpreter, so the server's memory is in a child process."""
    kernel = ctypes.WinDLL("kernel32")
    kernel.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_ProcessEntry)]
    snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    children: dict[int, list[int]] = {}
    entry = _ProcessEntry()
    entry.dwSize = ctypes.sizeof(entry)
    more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
    while more:
        children.setdefault(entry.ppid, []).append(entry.pid)
        more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    kernel.CloseHandle(ctypes.c_void_p(snapshot))
    tree, queue = [], [pid]
    while queue:
        tree.append(queue[0])
        queue.extend(children.get(queue.pop(0), []))
    return tree


def _windows_rss_mb(pid: int) -> tuple[float, float] | None:
    kernel, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    kernel.OpenProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_Counters), ctypes.c_uint32]
    current = peak = 0.0
    for member in _windows_process_tree(pid):
        handle = kernel.OpenProcess(0x1010, False, member)  # QUERY_INFO | VM_READ
        if not handle:
            continue
        counters = _Counters()
        counters.cb = ctypes.sizeof(counters)
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            current += counters.WorkingSetSize / 1e6
            peak += counters.PeakWorkingSetSize / 1e6
        kernel.CloseHandle(ctypes.c_void_p(handle))
    return (current, peak) if peak else None


def process_rss_mb(pid: int) -> tuple[float, float] | None:
    """(current, peak) resident MB of the server process tree, or None."""
    if sys.platform.startswith("linux"):
        fields = {}
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith(("VmRSS", "VmHWM")):
                fields[line.split(":")[0]] = int(line.split()[1]) / 1024
        return fields["VmRSS"], fields["VmHWM"]
    if sys.platform == "win32":
        return _windows_rss_mb(pid)
    return None


def machine_memory_mb() -> tuple[float, float] | None:
    """(available, total) physical memory in MB, or None if unsupported."""
    if sys.platform.startswith("linux"):
        lines = Path("/proc/meminfo").read_text().splitlines()
        info = {k: int(v.split()[0]) / 1024 for k, v in (
            line.split(":", 1) for line in lines)}
        return info["MemAvailable"], info["MemTotal"]
    if sys.platform == "win32":
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32),
                        ("total", ctypes.c_uint64), ("avail", ctypes.c_uint64),
                        ("tpage", ctypes.c_uint64), ("apage", ctypes.c_uint64),
                        ("tvirt", ctypes.c_uint64), ("avirt", ctypes.c_uint64),
                        ("ext", ctypes.c_uint64)]
        status = Status()
        status.length = ctypes.sizeof(status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))  # type: ignore[attr-defined]
        return status.avail / 1e6, status.total / 1e6
    return None


# --------------------------------------------------------------------- the run


def load_fixture(database_url: str, nodes: int, mean_text: int, edges: int) -> dict:
    conn = psycopg2.connect(database_url)
    try:
        with conn, conn.cursor() as cur:
            for statement in fixture_statements(nodes, mean_text, edges):
                cur.execute(statement)
            cur.execute(
                "SELECT count(*), coalesce(sum(length(text)), 0)"
                f" FROM document_nodes WHERE repo_id = '{REPO_ID}'")
            n, text_bytes = cur.fetchone()  # type: ignore[misc]
            cur.execute(
                "SELECT count(*) FROM document_relationships"
                f" WHERE repo_id = '{REPO_ID}'")
            rels = cur.fetchone()[0]  # type: ignore[index]
    finally:
        conn.close()
    return {"nodes": n, "text_mb": round(int(text_bytes) / 1e6, 1),
            "relationships": rels}


class Server:
    """The real ingestion_service app in one uvicorn process (like the Dockerfile)."""

    def __init__(self, root: Path, database_url: str, port: int):
        service_dir = root / "ingestion_service"
        env = dict(os.environ, DATABASE_URL=database_url,
                   PYTHONPATH=os.pathsep.join([str(root), str(service_dir)]))
        self.base = f"http://127.0.0.1:{port}"
        self.errors = tempfile.TemporaryFile("w+")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.api.v1.main:app",
             "--port", str(port), "--log-level", "warning"],
            cwd=service_dir, env=env, stdout=subprocess.DEVNULL,
            stderr=self.errors)
        for _ in range(240):
            if self.proc.poll() is not None:
                self.errors.seek(0)
                raise RuntimeError(
                    f"ingestion_service exited ({self.proc.returncode}): "
                    + self.errors.read()[-1500:])
            try:
                if httpx.get(f"{self.base}/version", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.5)
        self.stop()
        raise RuntimeError("ingestion_service did not start")

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(15)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def run_level(server: Server, level: int) -> dict:
    """`level` simultaneous exports plus a /version probe every 50 ms."""
    probes: list[tuple[float, float, bool]] = []
    stop = threading.Event()
    exports: list[tuple[float, int, str]] = []

    def probe() -> None:
        with httpx.Client(timeout=300) as client:
            while not stop.is_set():
                started = time.perf_counter()
                try:
                    ok = client.get(f"{server.base}/version").status_code == 200
                except httpx.HTTPError:
                    ok = False
                probes.append((started, time.perf_counter() - started, ok))
                time.sleep(0.05)

    def export() -> None:
        started = time.perf_counter()
        r = httpx.get(f"{server.base}/v1/graph/repos/{REPO_ID}", timeout=900)
        exports.append((time.perf_counter() - started, r.status_code,
                        canonical_hash(r.content)))

    prober = threading.Thread(target=probe)
    prober.start()
    time.sleep(0.3)
    idle = process_rss_mb(server.proc.pid)
    t0 = time.perf_counter()
    workers = [threading.Thread(target=export) for _ in range(level)]
    [w.start() for w in workers]
    [w.join() for w in workers]
    t1 = time.perf_counter()
    stop.set()
    prober.join()
    peak = process_rss_mb(server.proc.pid)
    window = [p for p in probes if t0 <= p[0] <= t1]
    return {
        "concurrent_exports": level,
        "export_seconds": summarize([e[0] for e in exports]),
        "wall_seconds": round(t1 - t0, 2),
        "statuses": sorted({e[1] for e in exports}),
        "response_hashes": sorted({e[2] for e in exports}),
        "version_probe_max_seconds": round(max(p[1] for p in window), 2),
        "version_probe_failures": sum(1 for p in window if not p[2]),
        "idle_rss_mb": round(idle[0]) if idle else None,
        "peak_rss_mb": round(peak[1]) if peak else None,
    }


def describe_environment(root: Path) -> dict:
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                              text=True).stdout.strip()
    memory = machine_memory_mb()
    return {
        "git_sha": git("rev-parse", "HEAD")[:12],
        "git_dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "platform": platform.platform(), "python": platform.python_version(),
        "cpus": os.cpu_count(),
        "machine_total_mb": round(memory[1]) if memory else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--database-url", default=os.environ.get("BENCH_DATABASE_URL"))
    ap.add_argument("--nodes", type=int, default=15000)
    ap.add_argument("--mean-text-bytes", type=int, default=2000)
    ap.add_argument("--edges-per-node", type=int, default=3)
    ap.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4])
    ap.add_argument("--port", type=int, default=8110)
    ap.add_argument("--repo-root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--headroom", type=float, default=1.25,
                    help="safety factor on projected memory before a level runs")
    ap.add_argument("--expect-hash", help="fail unless the response hash matches")
    ap.add_argument("--skip-load", action="store_true", help="reuse loaded fixture")
    ap.add_argument("--force-db", action="store_true",
                    help="allow a database whose name isn't test/bench-like")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    if not args.database_url:
        ap.error("set BENCH_DATABASE_URL or pass --database-url")
    check_database_url(args.database_url, args.force_db)
    args.repo_root = args.repo_root.resolve()  # the server runs in another cwd
    levels = sorted(set(args.levels) | {1})

    fixture = (None if args.skip_load else load_fixture(
        args.database_url, args.nodes, args.mean_text_bytes, args.edges_per_node))
    print("fixture:", fixture or "reused", flush=True)
    warm = Server(args.repo_root, args.database_url, args.port)  # warm the DB cache
    httpx.get(f"{warm.base}/v1/graph/repos/{REPO_ID}", timeout=900)
    warm.stop()

    results, per_export_mb = [], None
    for level in levels:
        memory = machine_memory_mb()
        if per_export_mb is not None and memory is not None:
            need = projected_peak_mb(results[0]["idle_rss_mb"], per_export_mb,
                                     level, args.headroom)
            if need > memory[0]:
                results.append({"concurrent_exports": level, "skipped": (
                    f"projected {need:.0f} MB exceeds {memory[0]:.0f} MB available")})
                print(results[-1], flush=True)
                continue
        server = Server(args.repo_root, args.database_url, args.port)
        try:
            result = run_level(server, level)
        finally:
            server.stop()
        if level == 1 and result["peak_rss_mb"]:
            per_export_mb = result["peak_rss_mb"] - result["idle_rss_mb"]
        results.append(result)
        print(json.dumps(result), flush=True)

    hashes = {h for r in results for h in r.get("response_hashes", [])}
    report = {"environment": describe_environment(args.repo_root),
              "fixture": fixture, "results": results, "distinct_hashes": sorted(hashes)}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if len(hashes) != 1 or (args.expect_hash and hashes != {args.expect_hash}):
        print(f"RESPONSE MISMATCH: {sorted(hashes)}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
