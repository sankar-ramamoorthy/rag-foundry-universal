"""F-07 baseline/verification harness.

Builds a RepoGraph over (1) a fixture repo exercising tricky AST cases and
(2) a synthetic repo for timing. Dumps entities+relationships to JSON so
before/after refactor outputs can be diffed byte-for-byte (ADR-030).

Usage: python graph_baseline.py <out.json>  (run from ingestion_service/)
"""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, ".")
from src.core.codebase.repo_graph_builder import RepoGraphBuilder  # noqa: E402

SCRATCH = Path(tempfile.gettempdir()) / "f07-graph-baseline"
SCRATCH.mkdir(exist_ok=True)

FIXTURE_FILES = {
    "app/service.py": (
        "import os\n"
        "from pathlib import Path\n"
        "\n"
        "\n"
        "def helper(x):\n"
        "    return x + 1\n"
        "\n"
        "\n"
        "class Service:\n"
        "    \"\"\"docstring with unicode: café\"\"\"\n"
        "\n"
        "    def run(self):\n"
        "        value = helper(2)\n"
        "        self.finish(value)\n"
        "        return value\n"
        "\n"
        "    def finish(self, v):\n"
        "        print(v)\n"
        "\n"
        "    class Inner:\n"
        "        def ping(self):\n"
        "            return helper(0)\n"
    ),
    "app/decorated.py": (
        "import functools\n"
        "\n"
        "\n"
        "@functools.lru_cache(maxsize=None)\n"
        "def cached(n):\n"
        "    return n * 2\n"
        "\n"
        "\n"
        "def oneliner(): return cached(1)\n"
    ),
    # form feed (\f) between functions — ast page-break edge case
    "app/formfeed.py": (
        "def first():\n"
        "    return 1\n"
        "\f\n"
        "def second():\n"
        "    return first()\n"
    ),
    "docs/guide.md": (
        "# Service\n"
        "\n"
        "The Service class.\n"
        "\n"
        "## helper\n"
        "\n"
        "Adds one.\n"
    ),
}


def write_fixture(root: Path):
    for rel, content in FIXTURE_FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content.encode("utf-8"))
    # one CRLF file, written raw so newline handling is exercised
    crlf = root / "app" / "windows.py"
    crlf.write_bytes(b"def win():\r\n    return 42\r\n")


def write_synthetic(root: Path, n_files=40, n_funcs=30):
    for i in range(n_files):
        lines = [f"import mod{(i + 1) % n_files}\n\n"]
        for j in range(n_funcs):
            lines.append(
                f"def func_{i}_{j}(a, b):\n"
                f"    x = a + b\n"
                f"    return func_{i}_{(j + 1) % n_funcs}(x, b)\n\n"
            )
        lines.append(f"class Klass{i}:\n")
        for j in range(5):
            lines.append(
                f"    def method_{j}(self):\n"
                f"        return func_{i}_{j}(1, 2)\n\n"
            )
        (root / f"mod{i}.py").write_text("".join(lines), encoding="utf-8")


def dump_graph(root: Path) -> dict:
    graph = RepoGraphBuilder(root, ingestion_id="fixed-ingestion-id").build()
    entities = {
        cid: {
            "artifact_type": e.get("artifact_type"),
            "name": e.get("name"),
            "parent_id": e.get("parent_id"),
            "id": e.get("id"),
            "text": e.get("text"),
            "doc_type": e.get("doc_type"),
            "title": e.get("title"),
        }
        for cid, e in sorted(graph.entities.items())
    }
    relationships = sorted(
        graph.relationships,
        key=lambda r: json.dumps(r, sort_keys=True, default=str),
    )
    return {"entities": entities, "relationships": relationships}


def main(out_path: str):
    n_files = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    fixture_root = SCRATCH / "fixture_repo"
    write_fixture(fixture_root)
    result = dump_graph(fixture_root)

    synth_root = SCRATCH / f"synthetic_repo_{n_files}"
    if not synth_root.exists():
        synth_root.mkdir()
        write_synthetic(synth_root, n_files=n_files)
    t0 = time.perf_counter()
    graph = RepoGraphBuilder(synth_root, ingestion_id="timing-run").build()
    elapsed = time.perf_counter() - t0
    stats = {
        "synthetic_entities": len(graph.entities),
        "synthetic_relationships": len(graph.relationships),
        "synthetic_build_seconds": round(elapsed, 3),
    }

    Path(out_path).write_text(
        json.dumps({"stats": stats, **result}, indent=1, sort_keys=True,
                   default=str),
        encoding="utf-8",
    )
    print(json.dumps(stats))


if __name__ == "__main__":
    main(sys.argv[1])
