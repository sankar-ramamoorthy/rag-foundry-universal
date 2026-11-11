"""CI-06 (#337): embedding-input coverage and sampled discovery comparison.

Development corpora only. Runs the real extractor (``RepoGraphBuilder``) and
the shared chunker code, then measures two separate things:

* ``coverage``: which non-whitespace artifact characters reach at least one
  effective embedding input (the text the model actually encodes), per
  chunking contract. No network.
* ``retrieval``: a sampled needle-style discovery comparison. Queries are
  source lines; the gap set uses lines that the legacy contract never
  embeds, the control set uses lines every contract embeds. Embeddings come
  from a local Ollama (``--ollama``, default ``http://localhost:11434``)
  and are cached by input hash so contracts sharing a passage share a vector.

The legacy contract is frozen here (heuristic-v1 selection + the former
800-character / 400-word client truncation from commit 75c3b4c) because the
shared code no longer implements it.

    DATABASE_URL=postgresql://unused/unused \\
      ./.venv/Scripts/python.exe scripts/ci06_embedding_coverage.py coverage \\
      --repo . --json OUT.json
    ... retrieval --repo . --sample 60 --distractors 140 --cache DIR --json OUT
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ingestion_service"))
os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost/unused")

from shared.chunkers.selector import ChunkerFactory  # noqa: E402
from shared.chunkers.text import (  # noqa: E402
    TextChunker,
    estimate_tokens,
    line_windows,
    split_for_overflow,
)

WS = re.compile(r"\s+")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
LEGACY_MAX_CHARS = 800
LEGACY_MAX_WORDS = 400
MODEL = "mxbai-embed-large:latest"


# --------------------------------------------------------------------------
# Artifacts
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Artifact:
    canonical_id: str
    doc_type: str
    relative_path: str
    text: str

    @property
    def is_code(self) -> bool:
        return "source" in (self.doc_type or "")


def load_artifacts(repo: Path) -> list[Artifact]:
    logging.disable(logging.CRITICAL)
    repo = repo.resolve()
    previous = Path.cwd()
    # Service settings read ./.env; the root .env carries non-ingestion keys.
    os.chdir(ROOT / "ingestion_service")
    try:
        from src.core.codebase.repo_graph_builder import (  # pyright: ignore[reportMissingImports]
            RepoGraphBuilder,
        )

        graph = RepoGraphBuilder(
            repo_root=repo,
            ingestion_id="00000000-0000-0000-0000-000000000000",
        ).build()
    finally:
        os.chdir(previous)
    return [
        Artifact(e["canonical_id"], e.get("doc_type") or "", e["relative_path"],
                 e["text"])
        for e in graph.all_entities()
        if (e.get("text") or "").strip()
    ]


# --------------------------------------------------------------------------
# Contracts: artifact text -> (strategy label, effective embedding inputs)
# --------------------------------------------------------------------------
_LEGACY = {
    "sentence": TextChunker(chunk_strategy="sentence"),
    "paragraph": TextChunker(chunk_strategy="paragraph"),
    "simple": TextChunker(chunk_strategy="simple"),
}


def _legacy_units(text: str) -> tuple[str, list[str]]:
    """Frozen heuristic-v1 selection (shared/chunkers/selector.py @ 75c3b4c)."""
    if len(text) < 2000:
        name, params = "sentence", {"chunk_size": 200, "overlap": 20}
    elif len(text) < 10000:
        name, params = "paragraph", {"chunk_size": 500, "overlap": 50}
    else:
        name, params = "simple", {"chunk_size": 1000, "overlap": 100}
    return name, [c.content for c in _LEGACY[name].chunk(text, **params)]


def _legacy_truncate(text: str) -> str:
    """Frozen shared/embedders/ollama.py::_truncate @ 75c3b4c."""
    if len(text) > LEGACY_MAX_CHARS:
        text = text[:LEGACY_MAX_CHARS]
    words = text.split()
    if len(words) <= LEGACY_MAX_WORDS:
        return text
    return " ".join(words[:LEGACY_MAX_WORDS])


def legacy(text: str) -> tuple[str, list[str], list[str]]:
    name, units = _legacy_units(text)
    return name, units, [_legacy_truncate(u) for u in units]


def capped(budget: int) -> Callable[[str], tuple[str, list[str], list[str]]]:
    """Legacy units, but every unit fits the budget; no truncation."""

    def run(text: str) -> tuple[str, list[str], list[str]]:
        name, units = _legacy_units(text)
        if name == "simple":
            units = [c.content for c in _LEGACY["simple"].chunk(
                text, chunk_size=budget, overlap=100)]
        out: list[str] = []
        for unit in units:
            out.extend([unit] if len(unit) <= budget else line_windows(unit, budget, 0))
        return name, out, out

    return run


def factory(source_type: str | None):
    """Whatever shared ChunkerFactory does now; the embedder no longer truncates.

    ``source_type=None`` is the document heuristic with every unit fitted to
    the contract; ``"code"`` is the repository-artifact path.
    """

    def run(text: str) -> tuple[str, list[str], list[str]]:
        context = {"source_type": source_type} if source_type else {}
        chunker, params = ChunkerFactory.choose_strategy(text, **context)
        units = [c.content for c in chunker.chunk(text, **params)]
        return chunker.chunk_strategy, units, units

    return run


def unfitted(text: str) -> tuple[str, list[str], list[str]]:
    """Legacy units with no truncation at all (the embedder alone fixed)."""
    name, units = _legacy_units(text)
    return name, units, units


def linewin(budget: int, overlap: int = 100, max_tokens: int | None = None):
    def run(text: str) -> tuple[str, list[str], list[str]]:
        units = line_windows(text, budget, overlap, max_tokens)
        return "line_window", units, units

    return run


def contracts(budgets: list[int], token_budgets: list[int]) -> dict[str, Callable]:
    out: dict[str, Callable] = {
        "legacy-v1": legacy,
        "unfitted": unfitted,
        "factory-docs": factory(None),
        "factory-code": factory("code"),
    }
    for b in budgets:
        out[f"capped@{b}"] = capped(b)
        out[f"linewin@{b}"] = linewin(b)
        for t in token_budgets:
            out[f"linewin@{b}/t{t}"] = linewin(b, max_tokens=t)
    return out


# --------------------------------------------------------------------------
# Token fit, judged by the serving model itself
# --------------------------------------------------------------------------
def serving_identity(base_url: str) -> dict:
    """Ollama version, model digest and context, recorded with fit evidence."""
    def get(path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{base_url.rstrip('/')}{path}", data=data)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)

    tags = get("/api/tags")["models"]
    show = get("/api/show", {"model": MODEL})
    return {
        "ollama_version": get("/api/version").get("version"),
        "model": MODEL,
        "digest": next((m["digest"] for m in tags if m["name"] == MODEL), None),
        "context_length": show["model_info"].get("bert.context_length"),
        "quantization": show["details"].get("quantization_level"),
    }


class ServingFit:
    """Which inputs the serving model rejects with ``truncate: false``.

    No offline tokenizer: an earlier offline WordPiece counter diverged from
    Ollama's llama.cpp tokenizer on long words and normalization (CI-06 review
    R3). Batches are bisected, so cost is about one embedding per input.
    """

    def __init__(self, base_url: str, batch: int = 64):
        self.base_url = base_url.rstrip("/")
        self.batch = batch
        self.requests = 0

    def _accepts(self, texts: list[str]) -> bool:
        body = json.dumps({"model": MODEL, "input": texts, "truncate": False})
        req = urllib.request.Request(
            f"{self.base_url}/api/embed", data=body.encode(),
            headers={"Content-Type": "application/json"},
        )
        for attempt in range(4):  # bounded retry for transient resets
            self.requests += 1
            try:
                with urllib.request.urlopen(req, timeout=600) as resp:
                    resp.read()
                return True
            except urllib.error.HTTPError as err:
                if b"exceeds the context length" in err.read():
                    return False
                raise
            except (ConnectionError, urllib.error.URLError):
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("unreachable")

    def _rejected(self, texts: list[str]) -> list[str]:
        if self._accepts(texts):
            return []
        if len(texts) == 1:
            return texts
        mid = len(texts) // 2
        return self._rejected(texts[:mid]) + self._rejected(texts[mid:])

    def rejected(self, texts: list[str]) -> set[str]:
        unique = sorted(set(texts))
        out: set[str] = set()
        for start in range(0, len(unique), self.batch):
            out.update(self._rejected(unique[start:start + self.batch]))
            if (start // self.batch) % 200 == 0:
                print(f"  fit {start}/{len(unique)}", flush=True)
        return out

    def split_until_accepted(self, text: str) -> list[str]:
        """Mirror of IngestionPipeline._embed_fitted for one rejected passage."""
        pieces = []
        for piece in split_for_overflow(text):
            pieces.extend(
                [piece] if self._accepts([piece]) else self.split_until_accepted(piece)
            )
        return pieces


def fit_report(artifacts: list[Artifact], fns: dict[str, Callable],
               fit: ServingFit) -> dict:
    report: dict = {}
    for label, fn in fns.items():
        inputs: dict[str, tuple[str, bool]] = {}
        for art in artifacts:
            for text in fn(art.text)[2]:
                inputs.setdefault(text, (art.relative_path, art.is_code))
        print(f"[fit {label}] {len(inputs)} unique inputs", flush=True)
        rejected = fit.rejected(list(inputs))
        groups: dict = defaultdict(Counter)
        for text, (_, is_code) in inputs.items():
            g = groups["code" if is_code else "docs"]
            g["unique_inputs"] += 1
            g["rejected"] += text in rejected
        examples = sorted(
            (inputs[t][0], len(t), estimate_tokens(t)) for t in rejected
        )[:20]
        entry = {"groups": dict(groups), "rejected_examples": examples}
        if label.startswith("factory"):
            pieces = [len(fit.split_until_accepted(t)) for t in rejected]
            entry["split_pieces_added"] = sum(pieces) - len(pieces)
        report[label] = entry
    return report


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------
def covered_mask(text: str, inputs: list[str]) -> bytearray:
    """Mark non-whitespace characters of ``text`` present in some input.

    Inputs are located in order on whitespace-free text, so whitespace-only
    rewrites by the legacy sentence/paragraph chunkers do not count as loss.
    """
    norm = WS.sub("", text)
    mask = bytearray(len(norm))
    cursor = 0
    for raw in inputs:
        piece = WS.sub("", raw)
        if not piece:
            continue
        # Passages are emitted in source order: never match before the
        # previous passage's start (repeated blocks would otherwise alias).
        at = norm.find(piece, cursor)
        if at < 0:
            at = norm.find(piece)
        if at < 0:
            continue
        mask[at:at + len(piece)] = b"\x01" * len(piece)
        cursor = at
    return mask


def coverage_report(artifacts: list[Artifact], fns: dict[str, Callable]) -> dict:
    report: dict = {}
    for label, fn in fns.items():
        groups: dict = defaultdict(Counter)
        sizes: list[int] = []
        for art in artifacts:
            strategy, units, inputs = fn(art.text)
            mask = covered_mask(art.text, inputs)
            total, hit = len(mask), sum(mask)
            for key in ("code" if art.is_code else "docs", "all"):
                g = groups[key]
                g["artifacts"] += 1
                g["chars"] += total
                g["covered"] += hit
                g["fully_covered"] += hit == total
                g["passages"] += len(units)
                g["inputs_over_800"] += sum(len(i) > LEGACY_MAX_CHARS for i in inputs)
            groups["strategy:" + strategy]["artifacts"] += 1
            sizes.extend(len(i) for i in inputs)
        sizes.sort()
        report[label] = {
            "groups": {
                k: {**v, "coverage_pct": round(100 * v["covered"] / v["chars"], 3)
                    if v.get("chars") else None}
                for k, v in groups.items()
            },
            "input_chars": {
                "max": sizes[-1] if sizes else 0,
                "p50": sizes[len(sizes) // 2] if sizes else 0,
                "p99": sizes[int(len(sizes) * 0.99)] if sizes else 0,
            },
        }
    return report


# --------------------------------------------------------------------------
# Embeddings (local Ollama, cached)
# --------------------------------------------------------------------------
class Embeddings:
    def __init__(self, base_url: str, cache_path: Path):
        self.base_url = base_url.rstrip("/")
        self.cache_path = cache_path
        self.cache: dict[str, list[float]] = {}
        self.overflow: set[str] = set()
        self.seconds = 0.0
        self.computed = 0
        if cache_path.exists():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                self.cache[row["k"]] = row["v"]
                if row.get("overflow"):
                    self.overflow.add(row["k"])

    @staticmethod
    def key(text: str) -> str:
        return hashlib.sha256(f"{MODEL}\0{text}".encode()).hexdigest()

    def _post(self, texts: list[str], truncate: bool) -> list[list[float]]:
        body = json.dumps({"model": MODEL, "input": texts, "truncate": truncate})
        req = urllib.request.Request(
            f"{self.base_url}/api/embed", data=body.encode(),
            headers={"Content-Type": "application/json"},
        )
        for attempt in range(4):  # bounded retry for transient resets
            try:
                with urllib.request.urlopen(req, timeout=600) as resp:
                    return json.load(resp)["embeddings"]
            except (ConnectionError, urllib.error.URLError) as err:
                if isinstance(err, urllib.error.HTTPError) or attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("unreachable")

    def _store(self, text: str, vec: list[float], overflow: bool) -> None:
        k = self.key(text)
        self.cache[k] = vec
        row = {"k": k, "v": vec}
        if overflow:
            self.overflow.add(k)
            row["overflow"] = True
        with self.cache_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

    def ensure(self, texts: list[str], batch: int = 16, label: str = "") -> None:
        todo = sorted({t for t in texts if self.key(t) not in self.cache})
        print(f"[embed {label}] {len(todo)} new inputs", flush=True)
        for start in range(0, len(todo), batch):
            part = todo[start:start + batch]
            t0 = time.time()
            try:
                vecs = self._post(part, truncate=False)
                for text, vec in zip(part, vecs):
                    self._store(text, vec, False)
            except urllib.error.HTTPError:
                for text in part:  # isolate context-length overflow
                    try:
                        self._store(text, self._post([text], False)[0], False)
                    except urllib.error.HTTPError:
                        self._store(text, self._post([text], True)[0], True)
            self.seconds += time.time() - t0
            self.computed += len(part)
            if (start // batch) % 10 == 0:
                print(f"  {start + len(part)}/{len(todo)} "
                      f"{self.seconds / max(1, self.computed):.2f}s/input", flush=True)

    def vec(self, text: str) -> list[float]:
        return self.cache[self.key(text)]


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# --------------------------------------------------------------------------
# Retrieval experiment
# --------------------------------------------------------------------------
def _lines_with_offsets(text: str):
    """Yield (line, normalized start, normalized end) on whitespace-free text."""
    offset = 0
    for line in text.splitlines():
        n = len(WS.sub("", line))
        yield line, offset, offset + n
        offset += n


def _good_query_line(line: str) -> bool:
    s = line.strip()
    return (
        25 <= len(s) <= 160
        and len(set(IDENT.findall(s))) >= 2
        and not s.startswith(("#", "//", "import ", "from ", "*", "/*", '"""', "'''"))
    )


def ident_words(line: str) -> str:
    words: list[str] = []
    for ident in IDENT.findall(line):
        for part in re.split(r"_+|(?<=[a-z0-9])(?=[A-Z])", ident):
            if len(part) >= 2:
                words.append(part.lower())
    return " ".join(words)


def build_queries(arts: list[Artifact], all_arts: list[Artifact], rng: random.Random,
                  kind: str) -> list[dict]:
    path_of: dict[str, set[str]] = defaultdict(set)
    norm_all = [(a.relative_path, WS.sub("", a.text)) for a in all_arts]
    queries = []
    for art in arts:
        mask = covered_mask(art.text, legacy(art.text)[2])
        candidates = []
        for line, lo, hi in _lines_with_offsets(art.text):
            if hi <= lo or not _good_query_line(line):
                continue
            uncovered = not any(mask[lo:hi])
            if (kind == "gap") == uncovered and (kind == "gap" or all(mask[lo:hi])):
                candidates.append(line.strip())
        rng.shuffle(candidates)
        for line in candidates:
            needle = WS.sub("", line)
            if needle not in path_of:
                path_of[needle] = {p for p, t in norm_all if needle in t}
            if path_of[needle] == {art.relative_path}:
                queries.append({"kind": kind, "artifact": art.canonical_id,
                                "path": art.relative_path, "line": line})
                break
    return queries


def _rank_query(q: dict, corpus: list[Artifact], passages: list[tuple[str, str]],
                pvecs: list[list[float]], qvecs: dict, forms: dict) -> dict:
    """Artifact rank (max-pooled) and first exact-passage rank for one query."""
    needle = WS.sub("", q["line"])
    gold = {a.canonical_id for a in corpus if needle in WS.sub("", a.text)}
    row: dict = {"kind": q["kind"], "line": q["line"]}
    for form in forms:
        qv = qvecs[(q["line"], form)]
        scored = sorted(((_dot(qv, pv), i) for i, pv in enumerate(pvecs)),
                        reverse=True)
        seen: set[str] = set()
        art_rank = passage_rank = None
        for pos, (_, i) in enumerate(scored, 1):
            cid, text = passages[i]
            in_gold = cid in gold
            if passage_rank is None and in_gold and needle in WS.sub("", text):
                passage_rank = pos
            if cid not in seen:
                seen.add(cid)
                if art_rank is None and in_gold:
                    art_rank = len(seen)
            if art_rank and passage_rank:
                break
        row[form] = {"artifact_rank": art_rank, "passage_rank": passage_rank}
    return row


def evaluate(corpus: list[Artifact], queries: list[dict], fns: dict[str, Callable],
             emb: Embeddings) -> dict:
    qvecs = {}
    forms = {"verbatim": lambda q: q["line"], "words": lambda q: ident_words(q["line"])}
    emb.ensure([f(q) for q in queries for f in forms.values()], label="queries")
    for q in queries:
        for name, f in forms.items():
            qvecs[(q["line"], name)] = _unit(emb.vec(f(q)))

    results: dict = {}
    for label, fn in fns.items():
        passages: list[tuple[str, str]] = []
        for art in corpus:
            for text in fn(art.text)[2]:
                passages.append((art.canonical_id, text))
        emb.ensure([t for _, t in passages], label=label)
        pvecs = [_unit(emb.vec(t)) for _, t in passages]
        overflow = sum(emb.key(t) in emb.overflow for _, t in passages)
        per_query = [_rank_query(q, corpus, passages, pvecs, qvecs, forms)
                     for q in queries]
        results[label] = {
            "passages": len(passages),
            "overflow_inputs": overflow,
            "summary": summarize(per_query),
            "per_query": per_query,
        }
    return results


def _sign_test(wins: int, losses: int) -> float:
    """Exact two-sided sign test p-value (ties excluded)."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return round(min(1.0, 2 * tail), 4)


def paired(results: dict, baseline: str) -> dict:
    """Per-query artifact-rank comparison of each contract against baseline."""
    out: dict = {}
    base = results[baseline]["per_query"]
    for label, res in results.items():
        if label == baseline:
            continue
        for kind in ("gap", "control"):
            for form in ("verbatim", "words"):
                wins = losses = ties = 0
                for b, c in zip(base, res["per_query"]):
                    if b["kind"] != kind:
                        continue
                    rb = b[form]["artifact_rank"] or math.inf
                    rc = c[form]["artifact_rank"] or math.inf
                    wins += rc < rb
                    losses += rc > rb
                    ties += rc == rb
                out[f"{label} vs {baseline}: {kind}/{form}"] = {
                    "better": wins, "worse": losses, "same": ties,
                    "sign_test_p": _sign_test(wins, losses),
                }
    return out


def summarize(rows: list[dict]) -> dict:
    out: dict = {}
    for kind in ("gap", "control"):
        sub = [r for r in rows if r["kind"] == kind]
        for form in ("verbatim", "words"):
            for level in ("artifact_rank", "passage_rank"):
                ranks = [r[form][level] for r in sub]
                key = f"{kind}/{form}/{level.split('_')[0]}"
                out[key] = {
                    "n": len(ranks),
                    "hit@1": sum(1 for r in ranks if r and r <= 1),
                    "hit@5": sum(1 for r in ranks if r and r <= 5),
                    "hit@10": sum(1 for r in ranks if r and r <= 10),
                    "mrr": round(
                        sum(1 / r for r in ranks if r) / max(1, len(ranks)), 4
                    ),
                }
    return out


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["coverage", "fit", "retrieval"])
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--budgets", default="800")
    ap.add_argument("--token-budgets", default="",
                    help="estimate_tokens() caps for line windows, e.g. 400,480")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--sample", type=int, default=60)
    ap.add_argument("--distractors", type=int, default=140)
    ap.add_argument("--max-artifact-chars", type=int, default=12000)
    ap.add_argument("--seed", type=int, default=337)
    ap.add_argument("--cache", type=Path)
    ap.add_argument("--ollama", default="http://localhost:11434")
    ap.add_argument("--contracts", default="",
                    help="comma-separated subset of contract labels")
    args = ap.parse_args()

    budgets = [int(b) for b in args.budgets.split(",")]
    token_budgets = [int(t) for t in args.token_budgets.split(",") if t]
    fns = contracts(budgets, token_budgets)
    if args.contracts:
        fns = {k: v for k, v in fns.items() if k in args.contracts.split(",")}
    artifacts = load_artifacts(args.repo)
    print(f"artifacts: {len(artifacts)}", flush=True)

    if args.command == "coverage":
        out = {"repo": str(args.repo), "artifacts": len(artifacts),
               "report": coverage_report(artifacts, fns)}
    elif args.command == "fit":
        fit = ServingFit(args.ollama)
        out = {"repo": str(args.repo), "artifacts": len(artifacts),
               "serving": serving_identity(args.ollama),
               "report": fit_report(artifacts, fns, fit),
               "requests": fit.requests}
    else:
        if not args.cache:
            ap.error("retrieval requires --cache")
        rng = random.Random(args.seed)
        code = sorted((a for a in artifacts if a.is_code
                       and len(a.text) <= args.max_artifact_chars),
                      key=lambda a: a.canonical_id)
        gap_pool = [a for a in code if sum(covered_mask(a.text, legacy(a.text)[2]))
                    < len(WS.sub("", a.text))]
        full_pool = [a for a in code if a not in set(gap_pool)]
        gap_arts = rng.sample(gap_pool, min(args.sample, len(gap_pool)))
        ctrl_arts = rng.sample(full_pool, min(args.sample, len(full_pool)))
        chosen = {a.canonical_id for a in gap_arts + ctrl_arts}
        rest = [a for a in code if a.canonical_id not in chosen]
        distract = rng.sample(rest, min(args.distractors, len(rest)))
        corpus = gap_arts + ctrl_arts + distract
        queries = (build_queries(gap_arts, artifacts, rng, "gap")
                   + build_queries(ctrl_arts, artifacts, rng, "control"))
        print(f"corpus {len(corpus)} artifacts, {len(queries)} queries", flush=True)
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        emb = Embeddings(args.ollama, args.cache)
        results = evaluate(corpus, queries, fns, emb)
        out = {
            "repo": str(args.repo), "seed": args.seed, "model": MODEL,
            "corpus_artifacts": len(corpus), "gap_pool": len(gap_pool),
            "queries": queries,
            "results": results,
            "paired": paired(results, "legacy-v1") if "legacy-v1" in results else {},
            "embed_seconds_per_input": round(emb.seconds / max(1, emb.computed), 3),
        }
    text = json.dumps(out, indent=1)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text, encoding="utf-8")
    shown = out.get("results", out.get("report", {}))
    summary = {
        k: v.get("summary", v) if isinstance(v, dict) else v for k, v in shown.items()
    }
    print(json.dumps(summary, indent=1)[:20000])


if __name__ == "__main__":
    main()
