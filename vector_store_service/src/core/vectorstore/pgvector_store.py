# src/core/vectorstore/pgvector_store.py
from __future__ import annotations
from typing import Sequence, Iterable, List, Optional, Dict, Any
import re
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import logging

from src.core.vectorstore.base import RetagResult, VectorStore
from shared.models.vector import VectorRecord, VectorMetadata

logging.basicConfig(level=logging.DEBUG)


class PgVectorStore(VectorStore):
    SCHEMA = "ingestion_service"

    # HNSW search-time candidate list size (audit F-10 / WP-S4): higher =
    # better recall, slower query. 100 is comfortable for k <= 50.
    HNSW_EF_SEARCH = 100

    # Issue #150: a filtered query (repo_id/doc_type/source_type/language)
    # can silently return far fewer than `k` rows -- pgvector's HNSW index
    # scan applies the filter *during* the approximate graph traversal and
    # can give up before finding k filter-matching rows once the filter is
    # selective relative to the whole (multi-repo, shared) index. Confirmed
    # live: a repo_id-filtered LIMIT 200 query returned only 28 rows without
    # these settings, vs. the correct 200 with them (~17-24ms, vs. ~5ms
    # broken/incomplete or ~700ms with iterative_scan on but max_scan_tuples
    # left unbounded) -- see
    # DOCS/test_results/2026-09-15-hnsw-iterative-scan-issue-150.md.
    # relaxed_order (not strict_order) is fine here: RAG retrieval needs a
    # good candidate set, not byte-exact result ordering guarantees.
    HNSW_ITERATIVE_SCAN = "relaxed_order"
    HNSW_MAX_SCAN_TUPLES = 20000

    # WP-S4B (+ issue #64; WP-L6a added "language"): filter keys promoted
    # from JSONB to real indexed columns. The write path copies them out of
    # source_metadata, so filtering on the column and on the JSONB key are
    # equivalent for every row.
    TYPED_FILTER_COLUMNS = frozenset(
        {"repo_id", "doc_type", "source_type", "language", "ingestion_id"}
    )

    def __init__(self, dsn: str, dimension: int, provider: str = "mock") -> None:
        self._dsn = dsn
        self._dimension = dimension
        self._provider = provider

    @property
    def dimension(self) -> int:
        return self._dimension

    def persist(self, records: list[VectorRecord]) -> None:
        self.add(records)
        logging.debug("PgVectorStore.persist: added %d records", len(records))

    def add(self, records: Iterable[VectorRecord]) -> None:
        """Write embeddings to vector_chunks (single write path).

        The legacy `vectors` table is retired (audit F-15): it was a
        never-removed MS6 dual-write target and is read nowhere in the
        query path. `document_id` is nullable, so records without one
        are still persisted.

        Idempotent (#287): a replayed batch is ignored row by row, so a
        client may safely resend a batch whose first attempt timed out
        after the server had already committed it.
        """
        records = list(records)
        chunks_sql = sql.SQL("""
            INSERT INTO {schema}.vector_chunks
            (vector, ingestion_id, chunk_id, chunk_index, chunk_strategy,
             chunk_text, source_metadata, provider, document_id,
             repo_id, doc_type, source_type, language)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ingestion_id, chunk_id, chunk_index) DO NOTHING
        """).format(schema=sql.Identifier(self.SCHEMA))

        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                for record in records:
                    source_metadata = record.metadata.source_metadata or {}
                    cur.execute(chunks_sql, (
                        record.vector, record.metadata.ingestion_id,
                        record.metadata.chunk_id, record.metadata.chunk_index,
                        record.metadata.chunk_strategy, record.metadata.chunk_text,
                        Jsonb(source_metadata),
                        record.metadata.provider or self._provider,
                        record.metadata.document_id or None,
                        # WP-S4B / issue #64 / WP-L6a (#85): typed copies of
                        # the filter-critical keys
                        source_metadata.get("repo_id"),
                        source_metadata.get("doc_type"),
                        source_metadata.get("source_type"),
                        source_metadata.get("language"),
                    ))
        logging.info(
            "PgVectorStore.add: %d records written to vector_chunks", len(records)
        )

    @classmethod
    def _filter_target(cls, key: str) -> sql.Composable:
        """SQL expression a filter key applies to: the typed column for
        promoted keys (WP-S4B), else the JSONB lookup."""
        if key in cls.TYPED_FILTER_COLUMNS:
            return sql.SQL("vc.{col}").format(col=sql.Identifier(key))
        return sql.SQL("vc.source_metadata->>{key}").format(
            key=sql.Literal(key)
        )

    @classmethod
    def _build_filter_conditions(
        cls, metadata_filter: Dict[str, Any]
    ) -> tuple[List[sql.Composable], List[Any]]:
        conditions: List[sql.Composable] = []
        filter_values: List[Any] = []

        for key, value in metadata_filter.items():
            target = cls._filter_target(key)

            if isinstance(value, dict):
                operator = list(value.keys())[0]
                operand = list(value.values())[0]

                if operator == "ne":
                    conditions.append(
                        sql.SQL(
                            "({target} IS NULL OR {target} != {val})"
                        ).format(target=target, val=sql.Placeholder())
                    )
                    filter_values.append(operand)

                elif operator == "in":
                    placeholders = sql.SQL(", ").join(
                        sql.Placeholder() for _ in operand
                    )
                    conditions.append(
                        sql.SQL("{target} IN ({vals})").format(
                            target=target, vals=placeholders
                        )
                    )
                    filter_values.extend(operand)

            else:
                # Simple equality
                conditions.append(
                    sql.SQL("{target} = {val}").format(
                        target=target, val=sql.Placeholder()
                    )
                )
                filter_values.append(value)

        return conditions, filter_values

    def similarity_search(
        self,
        query_vector: Sequence[float],
        k: int,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[VectorRecord]:
        """
        Search vector_chunks with optional metadata filtering.
        Uses cosine distance (<=>)  — correct for mxbai-embed-large and
        nomic-embed-text which both produce cosine-optimised embeddings.
        Score is returned as 1 - cosine_distance, range 0–1 (higher = more similar).

        metadata_filter supports:
            {"source_type": "code"}              → equality
            {"source_type": {"ne": "code"}}      → not equal (also matches NULL)
            {"doc_type": {"in": ["file","pdf"]}} → IN list

        repo_id / doc_type / source_type filter on their typed columns
        (WP-S4B, extended by issue #64); every other key filters on the
        source_metadata JSONB as before.
        """
        if metadata_filter:
            conditions, filter_values = self._build_filter_conditions(
                metadata_filter
            )
            where_clause = sql.SQL(" AND ").join(conditions)
            search_sql = sql.SQL("""
                WITH query AS (SELECT {qvec}::vector AS qvec)
                SELECT vc.vector, vc.ingestion_id, vc.chunk_id,
                       vc.chunk_index, vc.chunk_strategy,
                       vc.chunk_text, vc.source_metadata, vc.provider, vc.document_id,
                       1 - (vc.vector <=> query.qvec) AS score
                FROM {schema}.vector_chunks vc, query
                WHERE {where}
                ORDER BY vc.vector <=> query.qvec
                LIMIT {limit}
            """).format(
                schema=sql.Identifier(self.SCHEMA),
                where=where_clause,
                qvec=sql.Placeholder(),
                limit=sql.Placeholder(),
            )
            params = [query_vector] + filter_values + [k]
            use_iterative_scan = True

        else:
            use_iterative_scan = False
            search_sql = sql.SQL("""
                WITH query AS (SELECT {qvec}::vector AS qvec)
                SELECT vc.vector, vc.ingestion_id, vc.chunk_id,
                       vc.chunk_index, vc.chunk_strategy,
                       vc.chunk_text, vc.source_metadata, vc.provider, vc.document_id,
                       1 - (vc.vector <=> query.qvec) AS score
                FROM {schema}.vector_chunks vc, query
                ORDER BY vc.vector <=> query.qvec
                LIMIT {limit}
            """).format(
                schema=sql.Identifier(self.SCHEMA),
                qvec=sql.Placeholder(),
                limit=sql.Placeholder(),
            )
            params = [query_vector, k]

        results: List[VectorRecord] = []
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                # Transaction-scoped: applies only to this search.
                cur.execute(
                    sql.SQL("SET LOCAL hnsw.ef_search = {ef}").format(
                        ef=sql.Literal(self.HNSW_EF_SEARCH)
                    )
                )
                if use_iterative_scan:
                    # Issue #150: only a filtered search can under-recall
                    # this way -- an unfiltered scan has nothing to reject
                    # mid-traversal, so it's unaffected and left alone.
                    cur.execute(
                        sql.SQL("SET LOCAL hnsw.iterative_scan = {mode}").format(
                            mode=sql.Literal(self.HNSW_ITERATIVE_SCAN)
                        )
                    )
                    cur.execute(
                        sql.SQL(
                            "SET LOCAL hnsw.max_scan_tuples = {tuples}"
                        ).format(tuples=sql.Literal(self.HNSW_MAX_SCAN_TUPLES))
                    )
                cur.execute(search_sql, params)
                for row in cur.fetchall():
                    (vector, row_ingestion_id, chunk_id, chunk_index, chunk_strategy,
                     chunk_text, source_metadata, provider, document_id, score) = row
                    metadata = VectorMetadata(
                        ingestion_id=row_ingestion_id,
                        chunk_id=chunk_id,
                        chunk_index=chunk_index,
                        chunk_strategy=chunk_strategy,
                        chunk_text=chunk_text,
                        source_metadata=source_metadata,
                        provider=provider,
                        document_id=document_id,
                        score=score,
                    )
                    results.append(VectorRecord(vector=vector, metadata=metadata))
        # relaxed_order HNSW does not guarantee distance order.
        results.sort(key=lambda r: (-r.metadata.score, str(r.metadata.chunk_id)))
        return results

    def delete_by_ingestion_id(self, ingestion_id: str) -> None:
        # "vectors" is no longer written, but rows from before the F-15
        # dual-write removal may still exist — keep purging it until the
        # table is dropped by a migration.
        for table in ["vectors", "vector_chunks"]:
            delete_sql = sql.SQL("""
                DELETE FROM {schema}.{table_name} WHERE ingestion_id = %s
            """).format(
                schema=sql.Identifier(self.SCHEMA),
                table_name=sql.Identifier(table),
            )
            with psycopg.connect(self._dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(delete_sql, (ingestion_id,))

    # Issue #416 WP3: source-range patches are sent in bounded batches.
    RANGE_PATCH_BATCH = 500
    _SHA256 = re.compile(r"^[0-9a-f]{64}$")

    @classmethod
    def _validate_range_patches(
        cls, document_ids: List[str], patches: "dict[str, list[dict]] | None"
    ) -> "list[tuple]":
        """Flatten and validate source-range patches before any SQL runs, so a
        malformed request writes nothing. Returns (document_id, chunk_index,
        text_sha256, patch_dict) tuples where patch_dict holds only the location
        keys that may be written."""
        flat: list[tuple] = []
        seen: set = set()
        allowed = set(document_ids)
        for document_id, entries in (patches or {}).items():
            if document_id not in allowed:
                raise ValueError(
                    f"range patch for a document not retagged: {document_id}"
                )
            for entry in entries:
                index = entry.get("chunk_index")
                digest = entry.get("text_sha256")
                start, end = entry.get("start_line"), entry.get("end_line")
                reason = entry.get("range_reason")
                if type(index) is not int or index < 0:
                    raise ValueError("chunk_index must be a non-negative integer")
                if not isinstance(digest, str) or not cls._SHA256.match(digest):
                    raise ValueError("text_sha256 must be 64 lowercase hex digits")
                if (document_id, index) in seen:
                    raise ValueError(
                        f"duplicate range patch for {document_id}/{index}"
                    )
                seen.add((document_id, index))
                if start is not None or end is not None:
                    if (
                        type(start) is not int
                        or type(end) is not int
                        or not 1 <= start <= end
                        or reason is not None
                    ):
                        raise ValueError("a range needs 1 <= start_line <= end_line")
                    patch = {"start_line": start, "end_line": end}
                else:
                    if not isinstance(reason, str) or not reason or len(reason) > 200:
                        raise ValueError("no range needs a range_reason")
                    patch = {"range_reason": reason}
                flat.append((document_id, index, digest, patch))
        return flat

    def _patch_range_batch(self, cur, new_ingestion_id: str, batch: "list[tuple]"):
        """Patch one batch inside the caller's transaction. Only the three
        location keys of source_metadata are written; a row is touched only if
        it belongs to the new generation and its stored passage hashes to the
        digest the range was computed for. Returns the (document_id,
        chunk_index) pairs actually patched."""
        values = sql.SQL(", ").join(
            sql.SQL("(%s::uuid, %s::int, %s, %s::jsonb)") for _ in batch
        )
        statement = sql.SQL("""
            UPDATE {schema}.vector_chunks AS vc
            SET source_metadata = (
                vc.source_metadata - 'start_line' - 'end_line' - 'range_reason'
            ) || v.patch
            FROM (VALUES {values}) AS v(document_id, chunk_index, text_sha256, patch)
            WHERE vc.document_id = v.document_id
              AND vc.chunk_index = v.chunk_index
              AND vc.ingestion_id = %s
              AND encode(sha256(convert_to(vc.chunk_text, 'UTF8')), 'hex')
                  = v.text_sha256
            RETURNING vc.document_id, vc.chunk_index
        """).format(schema=sql.Identifier(self.SCHEMA), values=values)
        params: list = []
        for document_id, index, digest, patch in batch:
            params.extend([document_id, index, digest, Jsonb(patch)])
        params.append(new_ingestion_id)
        cur.execute(statement, params)
        return {(str(r[0]), int(r[1])) for r in cur.fetchall()}

    def _apply_range_patches(self, cur, new_ingestion_id: str, flat: "list[tuple]"):
        """Patch every batch, then explain each patch that did not apply. All of
        it runs in the caller's transaction, so a failure anywhere rolls back
        the retag and every earlier batch."""
        patched: set = set()
        size = max(1, int(self.RANGE_PATCH_BATCH))
        for start in range(0, len(flat), size):
            patched |= self._patch_range_batch(
                cur, new_ingestion_id, flat[start : start + size]
            )
        pending = [(d, i) for d, i, _, _ in flat if (d, i) not in patched]
        skipped: list = []
        if pending:
            cur.execute(
                sql.SQL("""
                    SELECT vc.document_id, vc.chunk_index
                    FROM {schema}.vector_chunks AS vc
                    WHERE vc.ingestion_id = %s AND vc.document_id = ANY(%s::uuid[])
                """).format(schema=sql.Identifier(self.SCHEMA)),
                (new_ingestion_id, sorted({d for d, _ in pending})),
            )
            present = {(str(r[0]), int(r[1])) for r in cur.fetchall()}
            for document_id, index in pending:
                skipped.append(
                    {
                        "document_id": document_id,
                        "chunk_index": index,
                        "reason": "digest mismatch"
                        if (document_id, index) in present
                        else "row not found at this generation",
                    }
                )
        return len(patched), skipped

    def retag_ingestion_id(
        self,
        document_ids: List[str],
        new_ingestion_id: str,
        provenance_by_document_id: "dict[str, dict] | None" = None,
        *,
        expected_ingestion_id: str,
        source_ranges_by_document_id: "dict[str, list[dict]] | None" = None,
    ) -> RetagResult:
        """Issue #196 (FR-007b, T024): re-tag reused artifacts' existing
        vector_chunks rows to the new generation's ingestion_id, in place.

        CI-06 review R2 (#337): fenced to ``expected_ingestion_id``, the prior
        generation whose vectors are being reused. A reused document_id can
        still carry rows of an older generation when best-effort cleanup of
        that generation failed; matching on document_id alone would relabel
        those stale rows into the new generation. Rows of any other
        generation are never touched. Returns the row count and the distinct
        document_ids actually retagged, so the caller can verify the reused
        set and re-embed anything missing.

        Issue #199 (Stage B2 incremental-reuse fix): document_ids present
        in `provenance_by_document_id` also get `source_metadata`'s
        `provenance` key replaced in the same statement, via `jsonb_set`
        (preserves every other existing key -- never a full overwrite).
        No embedding call, no row insert.
        """
        if not expected_ingestion_id:
            raise ValueError("expected_ingestion_id is required")
        if not document_ids:
            return RetagResult(0, [])
        # Issue #416 WP3: validated before any SQL, so a bad patch writes nothing.
        range_patches = self._validate_range_patches(
            document_ids, source_ranges_by_document_id
        )
        provenance_by_document_id = provenance_by_document_id or {}
        with_provenance = [d for d in document_ids if d in provenance_by_document_id]
        without_provenance = [
            d for d in document_ids if d not in provenance_by_document_id
        ]

        updated = 0
        retagged: set[str] = set()
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                if without_provenance:
                    plain_sql = sql.SQL("""
                        UPDATE {schema}.vector_chunks
                        SET ingestion_id = %s
                        WHERE document_id = ANY(%s) AND ingestion_id = %s
                        RETURNING document_id
                    """).format(schema=sql.Identifier(self.SCHEMA))
                    cur.execute(
                        plain_sql,
                        (new_ingestion_id, without_provenance, expected_ingestion_id),
                    )
                    rows = cur.fetchall()
                    updated += len(rows)
                    retagged.update(str(r[0]) for r in rows)

                if with_provenance:
                    values_sql = sql.SQL(", ").join(
                        sql.SQL("(%s::uuid, %s::jsonb)") for _ in with_provenance
                    )
                    # jsonb_set's path is a bound parameter (a one-element
                    # text[]), not spliced into the SQL text -- avoids any
                    # ambiguity between Postgres's '{...}' array-literal
                    # syntax and sql.SQL.format's own '{}' placeholders.
                    combined_sql = sql.SQL("""
                        UPDATE {schema}.vector_chunks AS vc
                        SET ingestion_id = %s,
                            source_metadata = jsonb_set(
                                vc.source_metadata, %s, v.provenance, true
                            )
                        FROM (VALUES {values}) AS v(document_id, provenance)
                        WHERE vc.document_id = v.document_id
                          AND vc.ingestion_id = %s
                        RETURNING vc.document_id
                    """).format(
                        schema=sql.Identifier(self.SCHEMA), values=values_sql
                    )
                    params: list = [new_ingestion_id, ["provenance"]]
                    for document_id in with_provenance:
                        params.append(document_id)
                        params.append(Jsonb(provenance_by_document_id[document_id]))
                    params.append(expected_ingestion_id)
                    cur.execute(combined_sql, params)
                    rows = cur.fetchall()
                    updated += len(rows)
                    retagged.update(str(r[0]) for r in rows)

                # Issue #416 WP3: the range patch shares this connection and so
                # this transaction. If anything above or below raises, the whole
                # request (retag included) rolls back; no row is left moved with
                # a stale or partial range.
                ranges_patched, ranges_skipped = 0, []
                if range_patches:
                    ranges_patched, ranges_skipped = self._apply_range_patches(
                        cur, new_ingestion_id, range_patches
                    )
        return RetagResult(
            updated, sorted(retagged), ranges_patched, ranges_skipped
        )

    def get_chunks_by_document_id(
        self, document_id: str, k: int = 3,
        query_vector: Optional[Sequence[float]] = None,
        ingestion_id: Optional[str] = None,
        repo_id: Optional[str] = None,
    ) -> List[VectorRecord]:
        """Exact distance ordering within one artifact, with stable ordinal ties.

        Materializing the scoped artifact avoids an approximate global ANN scan
        losing its tail passages. Only k rows cross the service boundary.
        """
        conditions = [sql.SQL("document_id = %s")]
        params: List[Any] = [document_id]
        if ingestion_id is not None:
            conditions.append(sql.SQL("ingestion_id = %s"))
            params.append(ingestion_id)
        if repo_id is not None:
            conditions.append(sql.SQL("repo_id = %s"))
            params.append(repo_id)
        score = sql.SQL("0.0")
        order = sql.SQL("chunk_index, chunk_id")
        if query_vector is not None:
            score = sql.SQL("1 - (vector <=> %s::vector)")
            params.append(list(query_vector))
            order = sql.SQL("score DESC, chunk_index, chunk_id")
        search_sql = sql.SQL("""
            WITH passages AS MATERIALIZED (
                SELECT * FROM {schema}.vector_chunks WHERE {conditions}
            )
            SELECT vector, ingestion_id, chunk_id, chunk_index, chunk_strategy,
                   chunk_text, source_metadata, provider, document_id,
                   {score} AS score
            FROM passages
            ORDER BY {order}
            LIMIT %s
        """).format(
            schema=sql.Identifier(self.SCHEMA),
            conditions=sql.SQL(" AND ").join(conditions),
            score=score, order=order,
        )
        params.append(k)
        results: List[VectorRecord] = []
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(search_sql, params)
                for row in cur.fetchall():
                    (vector, row_ingestion_id, chunk_id, chunk_index, chunk_strategy,
                     chunk_text, source_metadata, provider, document_id, score) = row
                    metadata = VectorMetadata(
                        ingestion_id=row_ingestion_id, chunk_id=chunk_id,
                        chunk_index=chunk_index, chunk_strategy=chunk_strategy,
                        chunk_text=chunk_text, source_metadata=source_metadata,
                        provider=provider, document_id=document_id, score=score,
                    )
                    results.append(VectorRecord(vector=vector, metadata=metadata))
        return results
