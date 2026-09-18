# src/core/vectorstore/pgvector_store.py
from __future__ import annotations
from typing import Sequence, Iterable, List, Optional, Dict, Any
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import logging

from src.core.vectorstore.base import VectorStore
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
        """
        records = list(records)
        chunks_sql = sql.SQL("""
            INSERT INTO {schema}.vector_chunks
            (vector, ingestion_id, chunk_id, chunk_index, chunk_strategy,
             chunk_text, source_metadata, provider, document_id,
             repo_id, doc_type, source_type, language)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
