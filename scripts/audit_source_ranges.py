"""Audit stored passage source ranges against the source at a pinned generation.

Issue #416 (specs/015-per-window-source-ranges, WP6). The guarantee being
checked: a passage that advertises a line range resolves, through Foundry's
public source reader, to the exact text of that passage at the same repository
generation. A range that cannot be established must be null with a stated
reason.

For a deterministic sample of passages that carry a range, the audit reads the
range back through ``GET /v1/repos/{id}/source/read`` at the pinned generation
and requires the returned lines to contain the passage text exactly. The lines
may include text before the passage on its first line and after it on its last
line (a passage window can start or end inside a line); nothing else may differ.
Every passage with no range is also checked: it must carry a reason from the
known set, and the counts per reason are reported.

Configuration comes only from arguments and environment variables, and nothing
private is defaulted or written to the result:

    FOUNDRY_ORCHESTRATOR_URL   base URL of the orchestrator (or --base-url)
    FOUNDRY_AUDIT_DSN          Postgres DSN, read-only use (or --dsn); standard
                               PG* variables work when no DSN is given

Two passage sources:

  * Database (read-only): lists the repository's passages at the generation
    with one SELECT. The connection is opened read-only and no write statement
    exists in this file. This is needed because passage text and ranges are not
    exposed by a public route.
  * ``--passages-json FILE``: a list of objects with ``path``, ``start_line``,
    ``end_line``, ``text`` (and optionally ``document_id``, ``chunk_index``,
    ``range_reason``). No database is needed, so a developer without database
    access can audit a captured set.

Example (values are placeholders):

    python scripts/audit_source_ranges.py --repo-id <uuid> --seed 416 \\
        --sample-size 1000 --acceptance --out audit.json

Exit status: 0 when every sampled range resolved and (with --acceptance) the
sample is at least 1,000; 1 when any range is wrong or the acceptance floor is
not met; 2 for usage or connection errors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

MIN_ACCEPTANCE_SAMPLE = 1000
DEFAULT_SAMPLE = 1000
PAGE_LINES = 500  # the source read API's per-request cap

# Reasons a passage legitimately has no range (spec 015 section 3), plus the
# ones written before #416, which older generations keep.
CURRENT_REASONS = frozenset(
    {
        "artifact range not verified",
        "window offset not reported",
        "passage does not match artifact text at reported offset",
        "passage split; range not established",
    }
)
LEGACY_REASONS = frozenset(
    {
        "line span not persisted at ingestion",
        "artifact split into several passages",
        "range not verified at ingestion",
    }
)
KNOWN_REASONS = CURRENT_REASONS | LEGACY_REASONS


@dataclass(frozen=True)
class Passage:
    document_id: str
    chunk_index: int
    path: str
    start_line: Optional[int]
    end_line: Optional[int]
    range_reason: Optional[str]
    text: Optional[str] = None

    @property
    def key(self) -> tuple:
        return (self.document_id, self.chunk_index, self.path, self.start_line or 0)

    @property
    def has_range(self) -> bool:
        return self.start_line is not None and self.end_line is not None


# --- the check itself ---


def contains_exactly(lines_text: str, first_len: int, last_len: int, text: str) -> bool:
    """True if ``text`` occurs in the joined lines starting on the first line
    and ending on the last line. Text before it on the first line and after it
    on the last line is allowed; a match that starts on a later line or ends on
    an earlier one does not count, so a window cannot be 'found' in lines it
    does not belong to."""
    if not text:
        return False
    i = lines_text.find(text)
    while i != -1:
        if i < first_len and i + len(text) > len(lines_text) - last_len:
            return True
        i = lines_text.find(text, i + 1)
    return False


def split_lf(text: str) -> list[str]:
    """Lines under the source read API's convention: LF only, terminators kept,
    no phantom line after a terminal LF."""
    if not text:
        return []
    parts = text.split("\n")
    out = [p + "\n" for p in parts[:-1]]
    if parts[-1]:
        out.append(parts[-1])
    return out


Reader = Callable[[str, int, int], dict]


def read_range(read: Reader, path: str, start: int, end: int) -> tuple[str, str, str]:
    """Read lines start..end through the source reader, paging at 500 lines.
    Returns (text, generation_id, error). The text digest of every page is
    verified against the reader's own ``returned_text_sha256``."""
    pieces: list[str] = []
    generation = ""
    cursor = start
    while cursor <= end:
        page_end = min(end, cursor + PAGE_LINES - 1)
        body = read(path, cursor, page_end)
        text = body.get("text")
        if not isinstance(text, str):
            return "", generation, "reader returned no text"
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != body.get("returned_text_sha256"):
            return "", generation, "returned text digest mismatch"
        generation = str(body.get("generation_id") or "")
        if body.get("start_line") != cursor:
            return "", generation, "reader returned a different start line"
        pieces.append(text)
        following = body.get("next_start_line")
        if following is None or following > end:
            break
        cursor = following
    return "".join(pieces), generation, ""


def verify_passage(read: Reader, passage: Passage, pinned: str) -> tuple[str, str]:
    """Outcome of one ranged passage: ('ok', '') or (kind, detail)."""
    if passage.text is None:
        return "no_text", "passage text unavailable"
    try:
        text, generation, error = read_range(
            read, passage.path, passage.start_line or 0, passage.end_line or 0
        )
    except ReadError as exc:
        return exc.kind, str(exc)
    if error:
        return "read_error", error
    if generation != pinned:
        return "generation_changed", f"{generation} != {pinned}"
    lines = split_lf(text)
    expected = (passage.end_line or 0) - (passage.start_line or 0) + 1
    # The API clamps a range that runs past the end of the file, so a cited range
    # that returns fewer lines than it names advertises lines that do not exist.
    if len(lines) != expected:
        return "range_out_of_bounds", f"{len(lines)} lines for {expected} cited"
    if contains_exactly(text, len(lines[0]), len(lines[-1]), passage.text):
        return "ok", ""
    return "mismatch", "passage text is not in the cited lines"


class ReadError(Exception):
    def __init__(self, kind: str, detail: str):
        super().__init__(detail)
        self.kind = kind


# --- deterministic sampling ---


def sample_passages(
    passages: Iterable[Passage], seed: int, size: int
) -> tuple[list[Passage], bool]:
    """A reproducible sample: the population is put in a total order first, so
    the result depends only on the seed, the size and the set of passages, never
    on the order they arrived in. Returns (sample, population_was_smaller)."""
    population = sorted(passages, key=lambda p: p.key)
    if size >= len(population):
        return population, size > len(population)
    return random.Random(seed).sample(population, size), False


# --- the audit ---


def audit_sample(
    sample: list[Passage],
    ranged_total: int,
    unranged: list[Passage],
    read: Reader,
    pinned: str,
    seed: int,
    requested: int,
    acceptance: bool,
    short: bool = False,
    ranged_with_reason: int = 0,
) -> dict:
    """Verify an already-chosen sample and report it against the population:
    ``ranged_total`` passages carry a range and ``unranged`` do not."""
    outcomes: Counter = Counter()
    failures: list[dict] = []
    for passage in sample:
        kind, detail = verify_passage(read, passage, pinned)
        outcomes[kind] += 1
        if kind != "ok" and len(failures) < 50:
            failures.append(
                {
                    "document_id": passage.document_id,
                    "chunk_index": passage.chunk_index,
                    "path": passage.path,
                    "start_line": passage.start_line,
                    "end_line": passage.end_line,
                    "outcome": kind,
                    "detail": detail,
                }
            )
    reasons: Counter = Counter(p.range_reason or "" for p in unranged)
    unexplained = sum(n for r, n in reasons.items() if r not in KNOWN_REASONS)
    incorrect = sum(n for k, n in outcomes.items() if k != "ok")
    total = ranged_total + len(unranged)
    eligible = total - reasons.get("artifact range not verified", 0)
    floor_met = len(sample) >= MIN_ACCEPTANCE_SAMPLE
    passed = (
        incorrect == 0
        and unexplained == 0
        and ranged_with_reason == 0
        and (floor_met or not acceptance)
    )
    return {
        "generation_id": pinned,
        "seed": seed,
        "sample_size_requested": requested,
        "sample_size_checked": len(sample),
        "population_smaller_than_sample": short,
        "acceptance_run": acceptance,
        "acceptance_floor": MIN_ACCEPTANCE_SAMPLE,
        "acceptance_floor_met": floor_met,
        "passages_total": total,
        "passages_with_range": ranged_total,
        "passages_without_range": len(unranged),
        "range_share_of_all": round(ranged_total / total, 6) if total else None,
        "range_share_of_eligible": round(ranged_total / eligible, 6)
        if eligible
        else None,
        "null_reasons": dict(sorted(reasons.items())),
        "null_without_reason_or_unknown": unexplained,
        "ranged_passages_that_also_carry_a_reason": ranged_with_reason,
        "outcomes": dict(sorted(outcomes.items())),
        "incorrect_ranges": incorrect,
        "failures_first_50": failures,
        "passed": passed,
    }


def audit(
    ranged: list[Passage],
    unranged: list[Passage],
    read: Reader,
    pinned: str,
    seed: int,
    sample_size: int,
    acceptance: bool,
) -> dict:
    """Sample the ranged passages deterministically, then audit the sample."""
    sample, short = sample_passages(ranged, seed, sample_size)
    return audit_sample(
        sample, len(ranged), unranged, read, pinned, seed, sample_size,
        acceptance, short, sum(1 for p in ranged if p.range_reason),
    )


# --- inputs ---


def passages_from_json(path: str) -> list[Passage]:
    with open(path, encoding="utf-8") as handle:
        rows = json.load(handle)
    out = []
    for i, row in enumerate(rows):
        out.append(
            Passage(
                document_id=str(row.get("document_id", "")),
                chunk_index=int(row.get("chunk_index", i)),
                path=str(row["path"]),
                start_line=row.get("start_line"),
                end_line=row.get("end_line"),
                range_reason=row.get("range_reason"),
                text=row.get("text"),
            )
        )
    return out


LIST_SQL = """
SELECT vc.document_id::text, vc.chunk_index, dn.relative_path,
       (vc.source_metadata->>'start_line')::int,
       (vc.source_metadata->>'end_line')::int,
       vc.source_metadata->>'range_reason'
FROM ingestion_service.vector_chunks AS vc
JOIN ingestion_service.document_nodes AS dn ON dn.document_id = vc.document_id
WHERE vc.ingestion_id = %s AND vc.repo_id = %s
ORDER BY vc.document_id, vc.chunk_index
"""
TEXT_SQL = """
SELECT vc.document_id::text, vc.chunk_index, vc.chunk_text
FROM ingestion_service.vector_chunks AS vc
WHERE vc.ingestion_id = %s AND vc.document_id = ANY(%s::uuid[])
"""


def passages_from_database(
    connect: Callable[..., Any], dsn: str, generation: str, repo_id: str
) -> list[Passage]:
    """List the repository's passages at the generation. One read-only SELECT;
    texts are fetched separately, only for the sample (see attach_texts)."""
    with connect(dsn) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(LIST_SQL, (generation, repo_id))
            rows = cur.fetchall()
    return [
        Passage(str(d), int(i), str(p), s, e, r) for d, i, p, s, e, r in rows
    ]


def attach_texts(
    connect: Callable[..., Any], dsn: str, generation: str, sample: list[Passage]
) -> list[Passage]:
    if not sample:
        return []
    documents = sorted({p.document_id for p in sample})
    texts: dict = {}
    with connect(dsn) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            for start in range(0, len(documents), 200):
                cur.execute(TEXT_SQL, (generation, documents[start : start + 200]))
                for document_id, index, text in cur.fetchall():
                    texts[(str(document_id), int(index))] = text
    return [
        Passage(
            p.document_id, p.chunk_index, p.path, p.start_line, p.end_line,
            p.range_reason, texts.get((p.document_id, p.chunk_index)),
        )
        for p in sample
    ]


# --- transport (public API only) ---


def http_reader(
    base_url: str, repo_id: str, generation: str, timeout: int = 60
) -> Reader:
    import requests

    base = base_url.rstrip("/")

    def read(path: str, start: int, end: int) -> dict:
        response = requests.get(
            f"{base}/v1/repos/{repo_id}/source/read",
            params={
                "generation_id": generation,
                "path": path,
                "start_line": start,
                "end_line": end,
            },
            timeout=timeout,
        )
        if response.status_code == 409:
            raise ReadError("generation_changed", "409 generation mismatch")
        if response.status_code >= 400:
            raise ReadError("read_error", f"HTTP {response.status_code}")
        return response.json()

    return read


def discover(base_url: str, repo_id: str, generation: Optional[str]) -> dict:
    """The pinned generation, its commit, and the deployed service versions. If
    no generation is given, the current ready one is read once and pinned for
    the whole audit."""
    import requests

    base = base_url.rstrip("/")
    params = {"limit": 1}
    if generation:
        params["generation_id"] = generation
    files = requests.get(
        f"{base}/v1/repos/{repo_id}/source/files", params=params, timeout=60
    )
    files.raise_for_status()
    envelope = files.json().get("envelope") or {}
    version = requests.get(f"{base}/version", timeout=30)
    return {
        "generation_id": envelope.get("generation_id") or generation,
        "commit_sha": envelope.get("commit_sha"),
        "orchestrator_version": version.json() if version.ok else None,
    }


def redacted_base(base_url: str) -> str:
    """A stable identifier that does not reveal the address."""
    return "sha256:" + hashlib.sha256(base_url.rstrip("/").encode()).hexdigest()[:12]


# --- command line ---


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--base-url", default=os.environ.get("FOUNDRY_ORCHESTRATOR_URL"))
    p.add_argument("--repo-id", required=True)
    p.add_argument("--generation-id", help="pin this generation (default: current)")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE)
    p.add_argument("--acceptance", action="store_true",
                   help=f"require a sample of at least {MIN_ACCEPTANCE_SAMPLE}")
    p.add_argument("--dsn", default=os.environ.get("FOUNDRY_AUDIT_DSN"))
    p.add_argument("--passages-json", help="audit a captured list instead of the DB")
    p.add_argument("--out", help="write the result JSON here")
    return p


def run(args: argparse.Namespace, connect: Optional[Callable[..., Any]] = None) -> int:
    if not args.base_url:
        print(
            "error: --base-url or FOUNDRY_ORCHESTRATOR_URL is required",
            file=sys.stderr,
        )
        return 2
    if args.acceptance and args.sample_size < MIN_ACCEPTANCE_SAMPLE:
        print(
            "error: an acceptance run needs --sample-size >= "
            f"{MIN_ACCEPTANCE_SAMPLE}",
            file=sys.stderr,
        )
        return 2
    try:
        info = discover(args.base_url, args.repo_id, args.generation_id)
    except Exception as exc:  # noqa: BLE001 - report, do not trace secrets
        print(f"error: could not reach the source API ({type(exc).__name__})",
              file=sys.stderr)
        return 2
    pinned = info["generation_id"]
    if not pinned:
        print("error: no generation could be pinned", file=sys.stderr)
        return 2

    if args.passages_json:
        everything = passages_from_json(args.passages_json)
        ranged = [p for p in everything if p.has_range]
        unranged = [p for p in everything if not p.has_range]
        sample_source = "passages-json"
    else:
        if connect is None:
            import psycopg

            connect = psycopg.connect
        dsn = args.dsn or ""
        if not dsn and not any(os.environ.get(k) for k in ("PGHOST", "PGSERVICE")):
            print("error: a database source needs --dsn, FOUNDRY_AUDIT_DSN or PG* "
                  "variables (or use --passages-json)", file=sys.stderr)
            return 2
        everything = passages_from_database(connect, dsn, pinned, args.repo_id)
        ranged = [p for p in everything if p.has_range]
        unranged = [p for p in everything if not p.has_range]
        sample_source = "database (read-only)"

    chosen, short = sample_passages(ranged, args.seed, args.sample_size)
    if not args.passages_json:
        chosen = attach_texts(connect, args.dsn or "", pinned, chosen)
    reader = http_reader(args.base_url, args.repo_id, pinned)
    result = audit_sample(
        chosen, len(ranged), unranged, reader, pinned, args.seed,
        args.sample_size, args.acceptance, short,
        sum(1 for p in ranged if p.range_reason),
    )
    result.update(
        {
            "tool": "scripts/audit_source_ranges.py",
            "repo_id": args.repo_id,
            "commit_sha": info["commit_sha"],
            "orchestrator_version": info["orchestrator_version"],
            "base_url": redacted_base(args.base_url),
            "passage_source": sample_source,
        }
    )
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(json.dumps({k: result[k] for k in (
        "generation_id", "seed", "sample_size_checked", "passages_total",
        "passages_with_range", "range_share_of_eligible", "incorrect_ranges",
        "passed")}, indent=2))
    return 0 if result["passed"] else 1


def main(argv: Optional[list[str]] = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
