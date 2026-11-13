"""Issue #354: validate service-root import resolution on a disposable corpus.

Builds the code graph of an extracted repository snapshot twice, in memory,
with the ingestion code in this checkout: once with Python project-root
discovery disabled (the pre-#354 behaviour) and once enabled. Nothing is
persisted and no service or database is contacted.

Records: node-id stability, every lost and added edge, whether each added
edge replaces a placeholder for the same symbol (same caller, relation and
name), project-root containment of every newly resolved target, the
`src.`-prefixed placeholders still unresolved, imports where the
repository-root interpretation shadows a different project-root module,
and a deterministic stratified sample of new CALL edges with their call-site
and definition lines for manual verification.

    python scripts/validate_354_import_resolution.py CORPUS_DIR --sample 36 \
        --out RAW/2026-11-12-354-import-resolution-validation.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def import_builder():
    sys.path.insert(0, str(ROOT / "ingestion_service"))
    cwd = os.getcwd()
    os.chdir(ROOT / "ingestion_service")  # Settings read .env from cwd
    try:
        from src.core.codebase import repo_graph_builder as rgb
    finally:
        os.chdir(cwd)
    return rgb


def build(rgb, corpus: Path, roots: bool):
    # Settings are read lazily during extraction: run from the service
    # directory, with a placeholder DATABASE_URL that is never connected to
    # (graph building is pure in-memory extraction and assembly).
    os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost/unused")
    cwd = os.getcwd()
    os.chdir(ROOT / "ingestion_service")
    original = rgb.RepoGraphBuilder._discover_python_project_roots
    if not roots:
        rgb.RepoGraphBuilder._discover_python_project_roots = lambda self: ()
    try:
        builder = rgb.RepoGraphBuilder(corpus, ingestion_id="validation-354")
        return builder, builder.build()
    finally:
        rgb.RepoGraphBuilder._discover_python_project_roots = original
        os.chdir(cwd)


def edge_key(r: dict) -> tuple[str, str, str]:
    return (r["from_canonical_id"], r["to_canonical_id"], r["relation_type"])


def last_name(cid: str) -> str:
    return cid.rsplit("#", 1)[-1].rsplit(".", 1)[-1].split(":")[-1]


def project_root_of(path: str, roots: tuple[str, ...]) -> str | None:
    parts = path.split("/")[:-1]
    while parts:
        if "/".join(parts) in roots:
            return "/".join(parts)
        parts.pop()
    return None


def line_at(corpus: Path, rel: str, lineno: int | None) -> str:
    if not lineno:
        return ""
    try:
        lines = (corpus / rel).read_text(encoding="utf-8").splitlines()
        return lines[lineno - 1].strip()
    except (OSError, IndexError):
        return ""


def definition_line(corpus: Path, cid: str) -> tuple[int | None, str]:
    rel, _, sym = cid.partition("#")
    name = sym.rsplit(".", 1)[-1]
    pattern = re.compile(rf"^\s*(?:async\s+)?(?:def|class)\s+{re.escape(name)}\b")
    try:
        for i, line in enumerate(
            (corpus / rel).read_text(encoding="utf-8").splitlines(), 1
        ):
            if pattern.match(line):
                return i, line.strip()
    except OSError:
        pass
    return None, ""


def shadowed_imports(graph, convention) -> list[dict]:
    """Level-0 imports in project files where the repository-root key and
    the project-root key both name modules, and they differ."""
    module_map = {}
    for e in graph.all_entities():
        if e.get("artifact_type") == "MODULE":
            dotted = convention.dotted_path(e["canonical_id"])
            if dotted:
                module_map[dotted] = e["canonical_id"]
    out = []
    for e in graph.all_entities():
        if e.get("artifact_type") != "IMPORT":
            continue
        meta, rel = e.get("metadata", {}), e.get("relative_path", "")
        local = convention.local_import_prefix(rel)
        if not local or (meta.get("level") or 0):
            continue
        base = meta.get("module", e.get("name", ""))
        for key in {base, f"{base}.{e.get('name', '')}"}:
            a, b = module_map.get(key), module_map.get(f"{local}.{key}")
            if a and b and a != b:
                out.append(
                    {"importer": rel, "import": key, "repo_root": a, "project_root": b}
                )
    return out


def reach(out: dict, start: str, rels: set[str], depth: int = 6) -> dict[str, int]:
    """BFS depth of every node reachable from `start` over `rels` edges."""
    seen = {start: 0}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        if seen[cur] >= depth:
            continue
        for target, rel in out[cur]:
            if rel in rels and target not in seen:
                seen[target] = seen[cur] + 1
                queue.append(target)
    return seen


def run(corpus: Path, sample_n: int) -> dict:  # noqa: C901 - one linear report
    rgb = import_builder()
    _, before = build(rgb, corpus, roots=False)
    builder, after = build(rgb, corpus, roots=True)
    roots = builder._discover_python_project_roots()
    convention = builder.assembler.module_convention

    ids_b = {e["canonical_id"] for e in before.all_entities()}
    ids_a = {e["canonical_id"] for e in after.all_entities()}
    eb = {edge_key(r): r for r in before.relationships}
    ea = {edge_key(r): r for r in after.relationships}
    lost, added = sorted(set(eb) - set(ea)), sorted(set(ea) - set(eb))

    lost_by = defaultdict(list)
    for f, t, rel in lost:
        lost_by[(f, rel)].append(t)
    violations = {
        "lost_non_placeholder": [],
        "added_without_matching_placeholder": [],
        "cross_project": [],
        "metadata_changed_on_kept_edge": [],
    }
    # OVERRIDES are computed from INHERITS, never from a placeholder: a new
    # one is legitimate only if the child class gained an INHERITS edge to
    # the class that defines the overridden method.
    new_inherits = {(f, t) for f, t, rel in added if rel == "INHERITS"}
    derived_overrides = []
    placeholder_respelled = []
    for f, t, rel in lost:
        if not t.startswith("EXTERNAL_"):
            violations["lost_non_placeholder"].append([f, t, rel])
    for f, t, rel in added:
        if rel == "OVERRIDES":
            child, parent = f.rsplit(".", 1)[0], t.rsplit(".", 1)[0]
            cfile, _, cname = child.partition("#")
            # A class nested in a function has canonical id `file#fn.Cls`
            # while its methods are `file#Cls.m` (pre-existing extractor
            # identity quirk), so match the class by trailing name too.
            derived = any(
                p == parent
                and fc.partition("#")[0] == cfile
                and (fc == child or fc.endswith("." + cname))
                for fc, p in new_inherits
            )
            target = (
                "derived_overrides" if derived else "added_without_matching_placeholder"
            )
            (
                derived_overrides
                if target == "derived_overrides"
                else violations[target]
            ).append([f, t, rel])
            continue
        if t.startswith("EXTERNAL_"):
            placeholder_respelled.append([f, t, rel])
            continue
        candidates = lost_by.get((f, rel), [])
        ok = (
            any(c.startswith("EXTERNAL_MODULE:") for c in candidates)
            if rel == "IMPORTS"
            else any(last_name(c) == last_name(t) for c in candidates)
        )
        if not ok:
            violations["added_without_matching_placeholder"].append([f, t, rel])
        caller_root = project_root_of(f, roots)
        target_root = project_root_of(t.split("#")[0], roots)
        if caller_root != target_root:
            violations["cross_project"].append([f, t, rel, caller_root, target_root])
    for k in set(eb) & set(ea):
        if eb[k].get("relationship_metadata") != ea[k].get("relationship_metadata"):
            if k[2] != "IMPORTS":  # IMPORTS pair lists may grow; reported separately
                violations["metadata_changed_on_kept_edge"].append(list(k))

    new_calls = [k for k in added if k[2] == "CALL"]
    strata = defaultdict(list)
    for k in new_calls:
        f = k[0]
        strata[(f.split("/")[0], "tests" if "/tests/" in f else "src")].append(k)
    sample, i = [], 0
    ordered = {
        s: sorted(v, key=lambda k: hashlib.sha256("|".join(k).encode()).hexdigest())
        for s, v in sorted(strata.items())
    }
    while len(sample) < sample_n and any(i < len(v) for v in ordered.values()):
        for v in ordered.values():
            if i < len(v) and len(sample) < sample_n:
                sample.append(v[i])
        i += 1
    sample_rows = []
    for f, t, _ in sample:
        meta = ea[(f, t, "CALL")]["relationship_metadata"]
        site = (meta.get("call_sites") or [None])[0]
        dline, dtext = definition_line(corpus, t)
        sample_rows.append(
            {
                "caller": f,
                "target": t,
                "confidence": meta.get("confidence"),
                "call_site": site,
                "call_line": line_at(corpus, f.split("#")[0], site),
                "definition_line": dline,
                "definition_text": dtext,
            }
        )

    def src_placeholders(g):
        rows = [
            edge_key(r)
            for r in g.relationships
            if r["relation_type"] == "CALL"
            and r["to_canonical_id"].startswith("EXTERNAL_SYMBOL:src.")
        ]
        return rows

    remaining = src_placeholders(after)
    remaining_reason = Counter(
        "caller_outside_any_project"
        if project_root_of(f.split("#")[0], roots) is None
        else "not_found_under_own_project_root"
        for f, _, _ in remaining
    )

    out = defaultdict(list)
    for r in after.relationships:
        out[r["from_canonical_id"]].append((r["to_canonical_id"], r["relation_type"]))
    chain_start = "rag_orchestrator/src/api/v1/routes.py#rag_endpoint"
    reached = reach(out, chain_start, {"CALL"})
    chain = [
        "rag_orchestrator/src/core/service.py#run_rag",
        "rag_orchestrator/src/core/service.py#resolve_repo_id_http",
        "shared/embedders/factory.py#get_embedder",
        "shared/embedders/ollama.py#OllamaEmbedder",
        "rag_orchestrator/src/core/service.py#hybrid_retrieve",
        "rag_orchestrator/src/core/service.py#_query_generation",
    ]

    def counts(g):
        c = Counter(r["relation_type"] for r in g.relationships)
        ext = sum(
            1
            for r in g.relationships
            if r["relation_type"] == "CALL"
            and r["to_canonical_id"].startswith("EXTERNAL_SYMBOL:")
        )
        return {
            "edges": dict(sorted(c.items())),
            "call_to_placeholder": ext,
            "src_prefixed_call_placeholders": len(src_placeholders(g)),
        }

    return {
        "schema": "validate_354_import_resolution.v1",
        "corpus": str(corpus.name),
        "git_head": os.popen(f'git -C "{ROOT}" rev-parse HEAD').read().strip(),
        "python_project_roots": list(roots),
        "before": {**counts(before), "nodes": len(ids_b)},
        "after": {**counts(after), "nodes": len(ids_a)},
        "node_ids_added": sorted(ids_a - ids_b),
        "node_ids_removed_non_placeholder": sorted(
            i for i in ids_b - ids_a if not i.startswith("EXTERNAL_")
        ),
        "node_ids_removed_placeholder": len(
            [i for i in ids_b - ids_a if i.startswith("EXTERNAL_")]
        ),
        "edges_lost": len(lost),
        "edges_added": len(added),
        "edges_added_by_type": dict(Counter(k[2] for k in added)),
        "derived_overrides": derived_overrides,
        "placeholder_respelled_edges": placeholder_respelled,
        "new_call_edges_by_stratum": {
            f"{a}/{b}": len(v) for (a, b), v in sorted(strata.items())
        },
        "violations": violations,
        "shadowed_imports": shadowed_imports(after, convention),
        "remaining_src_placeholders": len(remaining),
        "remaining_src_placeholders_by_reason": dict(remaining_reason),
        "remaining_src_placeholders_detail": [list(k) for k in remaining],
        "chain_from_rag_endpoint": {c: reached.get(c) for c in chain},
        "sample": sample_rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("corpus", type=Path)
    ap.add_argument("--sample", type=int, default=36)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    data = run(args.corpus.resolve(), args.sample)
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=1))
    summary = {
        k: data[k]
        for k in (
            "before",
            "after",
            "edges_lost",
            "edges_added",
            "edges_added_by_type",
            "remaining_src_placeholders",
            "remaining_src_placeholders_by_reason",
        )
    }
    summary["violations"] = {k: len(v) for k, v in data["violations"].items()}
    summary["shadowed"] = len(data["shadowed_imports"])
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
