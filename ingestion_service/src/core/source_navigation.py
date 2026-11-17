"""#379 bounded, snapshot-consistent access to existing persisted source.

Database ownership stays in ingestion_service. No filesystem/checkout, vector
chunks, parsing, new storage, or historical-generation fallback is used here.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from functools import lru_cache
from time import monotonic
from typing import Any
from uuid import UUID

from sqlalchemy import collate, create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from shared.models.document_node import DocumentNode as Node
from src.core.config import get_settings
from src.core.database_session import read_snapshot
from src.core.models import IngestionRequest as Ingestion

SOURCE_TYPES = frozenset(
    {
        "python source",
        "typescript source",
        "javascript source",
        "rust source",
        "java source",
    }
)
MAX_LINES = 500
MAX_TEXT = 128 * 1024
MAX_RESPONSE = 256 * 1024
MAX_SCAN = 1024 * 1024
MAX_QUERIES = 32
WINDOW = 32768
SECONDS = 5.0


class NavigationError(Exception):
    def __init__(self, status: int, code: str, message: str, **details):
        super().__init__(message)
        self.status = status
        self.body = {"error_code": code, "message": message, "details": details}


def invalid(message: str):
    raise NavigationError(400, "INVALID_REQUEST", message)


def validate_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError, TypeError):
        invalid("Repository and generation must be UUIDs")
        raise AssertionError("unreachable")


def validate_path(value: str, *, pattern=False) -> str:
    if not value or len(value) > 1024 or "\\" in value or "\x00" in value:
        invalid("Expected a bounded relative POSIX path")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        invalid("Absolute paths are not accepted")
    if any(p in ("", ".", "..") for p in value.split("/")):
        invalid("Empty, dot and traversal segments are not accepted")
    if pattern and any("**" in p and p != "**" for p in value.split("/")):
        invalid("Double star must occupy a complete path segment")
    return value


def glob_regex(pattern: str) -> str:
    """Only *, ?, and full-segment ** are syntax; all other text is literal."""
    validate_path(pattern, pattern=True)
    parts = pattern.split("/")
    output = "^"
    for index, part in enumerate(parts):
        if part == "**":
            output += ".*" if index == len(parts) - 1 else "([^/]+/)*"
        else:
            output += "".join(
                "[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c)
                for c in part
            )
            if index < len(parts) - 1:
                output += "/"
    return output + "$"


def readable(canonical_id, path, doc_type, has_text):
    return canonical_id == path and doc_type in SOURCE_TYPES and has_text


class Budget:
    def __init__(self, deadline=None):
        self.deadline = deadline if deadline is not None else monotonic() + SECONDS
        self.queries = 0
        self.scanned = 0

    def check(self):
        if monotonic() >= self.deadline:
            raise NavigationError(503, "DEADLINE_EXCEEDED", "Source read timed out")

    def execute(self, session, statement):
        self.check()
        if self.queries >= MAX_QUERIES:
            self.exhausted()
        self.queries += 1
        remaining = max(1, int((self.deadline - monotonic()) * 1000))
        # Transaction-control statements do not retrieve data or spend scan bytes.
        session.execute(text(f"SET LOCAL statement_timeout = {remaining}"))
        session.execute(text(f"SET LOCAL lock_timeout = {min(1000, remaining)}"))
        result = session.execute(statement)
        self.check()
        return result

    def exhausted(self):
        raise NavigationError(
            413,
            "SCAN_LIMIT_EXCEEDED",
            "Source navigation work budget exceeded",
            max_scan_bytes=MAX_SCAN,
            max_queries=MAX_QUERIES,
        )

    def window_size(self):
        self.check()
        # UTF8 has at most four bytes per character. Bound transfer BEFORE SQL.
        count = min(WINDOW, (MAX_SCAN - self.scanned) // 4)
        if count < 1:
            self.exhausted()
        return count


@lru_cache(maxsize=1)
def navigation_sessions():
    """A small read pool for the SAME database; bound acquisition as well as SQL.

    The general pool can wait 30 seconds. This pool waits at most one second,
    connects in at most two (libpq), and never exceeds four concurrent readers.
    Its time is charged to the caller's five-second logical-operation deadline.
    """
    engine = create_engine(
        get_settings().DATABASE_URL,
        pool_size=4,
        max_overflow=0,
        pool_timeout=1,
        connect_args={"connect_timeout": 2},
    )
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def snapshot():
    return read_snapshot(navigation_sessions())


def ready_generation(session, repo_id, expected, budget):
    rows = budget.execute(
        session,
        select(
            Node.ingestion_id,
            Ingestion.status,
            Ingestion.commit_sha,
        )
        .select_from(Node)
        .outerjoin(
            Ingestion,
            Node.ingestion_id == Ingestion.ingestion_id,
        )
        .where(Node.repo_id == repo_id)
        .distinct()
        .limit(2),
    ).all()
    if len(rows) > 1 or (rows and rows[0].status is None):
        raise NavigationError(503, "INCONSISTENT_SOURCE", "Invalid repository owner")
    if rows and rows[0].status == "completed":
        actual = str(rows[0].ingestion_id)
        if actual != expected:
            raise NavigationError(
                409,
                "GENERATION_MISMATCH",
                "Repository generation changed",
                repo_id=repo_id,
                expected_generation_id=expected,
                generation_id=actual,
                generation_status="ready",
            )
        return {
            "repo_id": repo_id,
            "generation_id": actual,
            "commit_sha": rows[0].commit_sha,
        }
    status = (
        rows[0].status
        if rows
        else budget.execute(
            session,
            select(Ingestion.status)
            .where(Ingestion.repo_id == repo_id)
            .order_by(Ingestion.created_at.desc(), Ingestion.ingestion_id.desc())
            .limit(1),
        ).scalar()
    )
    if status is None:
        raise NavigationError(404, "REPOSITORY_NOT_FOUND", "Repository not available")
    raise NavigationError(
        404,
        "GENERATION_UNAVAILABLE",
        "No completed source generation is available",
        generation_status="building" if status in ("accepted", "running") else status,
    )


def encode_cursor(repo, generation, pattern, after):
    raw = json.dumps([1, repo, generation, pattern, after], ensure_ascii=False)
    token = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    if len(token) > 4096:
        raise NavigationError(413, "RESPONSE_TOO_LARGE", "Cursor exceeds size limit")
    return token


def decode_cursor(cursor, repo, generation, pattern):
    if cursor is None:
        return None
    if len(cursor) > 4096:
        invalid("Cursor exceeds limit")
    try:
        raw = base64.b64decode(
            cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
        )
        fields = json.loads(raw)
        if not isinstance(fields, list) or len(fields) != 5:
            invalid("Invalid cursor")
        if fields[:4] != [1, repo, generation, pattern]:
            invalid("Cursor belongs to different repository, generation or pattern")
        after = validate_path(fields[4])
        if re.fullmatch(glob_regex(pattern), after) is None:
            invalid("Cursor path does not match filter")
        return after
    except (ValueError, TypeError, AttributeError, UnicodeError):
        invalid("Invalid cursor")


def find_files(
    repo_id, generation_id, pattern="**", limit=50, cursor=None, *, budget=None
):
    budget = budget or Budget()
    repo_id, generation_id = validate_uuid(repo_id), validate_uuid(generation_id)
    regex = glob_regex(pattern)
    if not 1 <= limit <= 200:
        invalid("Page size must be between 1 and 200")
    after = decode_cursor(cursor, repo_id, generation_id, pattern)
    with snapshot() as session:
        identity = ready_generation(session, repo_id, generation_id, budget)
        path = collate(Node.relative_path, "C")
        query = (
            select(
                Node.relative_path,
                Node.canonical_id,
                Node.document_id,
                Node.doc_type,
            func.octet_length(Node.text).isnot(None).label("has_text"),
            )
            .where(
                Node.repo_id == repo_id,
                Node.ingestion_id == generation_id,
                Node.canonical_id == Node.relative_path,
                func.length(Node.relative_path) <= 1024,
                path.op("~")(regex),
            )
            .order_by(path)
            .limit(limit + 1)
        )
        if after is not None:
            query = query.where(path > after)
        rows = budget.execute(session, query).all()
        files = [
            {
                "path": row.relative_path,
                "canonical_id": row.canonical_id,
                "document_id": str(row.document_id),
                "doc_type": row.doc_type,
                "source_status": "available"
                if readable(
                    row.canonical_id,
                    row.relative_path,
                    row.doc_type,
                    row.has_text,
                )
                else "unavailable",
            }
            for row in rows[:limit]
        ]
        budget.check()
        return dict(
            identity,
            files=files,
            next_cursor=(
                encode_cursor(repo_id, generation_id, pattern, files[-1]["path"])
                if len(rows) > limit
                else None
            ),
        )


def check_output_size(lines, size):
    if lines > MAX_LINES:
        raise NavigationError(413, "READ_TOO_LARGE", "Too many returned lines")
    if size > MAX_TEXT:
        raise NavigationError(413, "READ_TOO_LARGE", "Returned text exceeds cap")


def scan_source(fetch, source_bytes, start, end, budget, *, complete_request=False):
    """Read exact LF lines with bounded transfer and retained output, no line array."""
    if source_bytes == 0:
        if not complete_request:
            raise NavigationError(
                416, "INVALID_LINE_RANGE", "Empty source has no lines"
            )
        return "", 0, 0, True
    offset, line, consumed, returned, actual_end = 1, 1, 0, 0, 0
    pieces = []
    while consumed < source_bytes and (complete_request or line <= end):
        count = budget.window_size()
        block = fetch(offset, count)
        budget.check()
        if not block:
            raise NavigationError(
                503, "INCONSISTENT_SOURCE", "Source ended unexpectedly"
            )
        block_bytes = len(block.encode("utf-8"))
        budget.scanned += block_bytes
        if budget.scanned > MAX_SCAN:
            budget.exhausted()
        position = 0
        while position < len(block) and (complete_request or line <= end):
            budget.check()
            newline = block.find("\n", position)
            stop = len(block) if newline < 0 else newline + 1
            piece = block[position:stop]
            piece_bytes = len(piece.encode("utf-8"))
            consumed += piece_bytes
            if line >= start:
                returned += piece_bytes
                check_output_size(line - start + 1, returned)
                pieces.append(piece)
                actual_end = line
            if newline >= 0:
                line += 1
            position = stop
        offset += len(block)
    if actual_end == 0:
        raise NavigationError(416, "INVALID_LINE_RANGE", "Start line is beyond EOF")
    budget.check()
    return "".join(pieces), start, actual_end, consumed == source_bytes


def read_source(
    repo_id, generation_id, path, start_line=None, end_line=None, *, budget=None
):
    budget = budget or Budget()
    repo_id, generation_id = validate_uuid(repo_id), validate_uuid(generation_id)
    validate_path(path)
    complete_request = start_line is None and end_line is None
    if end_line is not None and start_line is None:
        invalid("end_line requires start_line")
    start = 1 if start_line is None else start_line
    end = start + MAX_LINES - 1 if end_line is None else end_line
    if start < 1 or end < start:
        raise NavigationError(416, "INVALID_LINE_RANGE", "Invalid line interval")
    if end - start + 1 > MAX_LINES:
        raise NavigationError(413, "READ_TOO_LARGE", "At most 500 lines per read")
    with snapshot() as session:
        identity = ready_generation(session, repo_id, generation_id, budget)
        conditions = (
            Node.repo_id == repo_id,
            Node.ingestion_id == generation_id,
            Node.canonical_id == path,
            Node.relative_path == path,
        )
        rows = budget.execute(
            session,
            select(
                Node.canonical_id,
                Node.document_id,
                Node.doc_type,
                Node.relative_path,
                func.octet_length(Node.text).label("source_bytes"),
            )
            .where(*conditions)
            .limit(2),
        ).all()
        if not rows:
            raise NavigationError(404, "FILE_NOT_FOUND", "File not found in generation")
        if len(rows) != 1:
            raise NavigationError(
                409, "AMBIGUOUS_PATH", "Multiple exact file identities"
            )
        node = rows[0]
        if not readable(
            node.canonical_id, path, node.doc_type, node.source_bytes is not None
        ):
            raise NavigationError(
                422, "SOURCE_UNAVAILABLE", "Stored source unavailable"
            )
        if complete_request and node.source_bytes > MAX_TEXT:
            raise NavigationError(
                413, "READ_TOO_LARGE", "Use line ranges for this file"
            )

        def fetch(offset, count):
            return budget.execute(
                session,
                select(
                    func.substr(Node.text, offset, count),
                ).where(*conditions),
            ).scalar_one()

        content, actual_start, actual_end, eof = scan_source(
            fetch,
            node.source_bytes,
            start,
            end,
            budget,
            complete_request=complete_request,
        )
        budget.check()
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        complete = eof and actual_start in (0, 1)
        budget.check()
        return dict(
            identity,
            path=path,
            canonical_id=node.canonical_id,
            document_id=str(node.document_id),
            doc_type=node.doc_type,
            representation="stored_source",
            start_line=actual_start,
            end_line=actual_end,
            complete_file=complete,
            next_start_line=None if eof else actual_end + 1,
            text=content,
            returned_text_sha256=digest,
            text_sha256=digest if complete else None,
            total_lines=actual_end if eof else None,
        )


def serialize(body: dict[str, Any], budget: Budget) -> bytes:
    budget.check()
    content = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    budget.check()
    if len(content) > MAX_RESPONSE:
        raise NavigationError(
            413, "RESPONSE_TOO_LARGE", "Serialized response exceeds cap"
        )
    return content
