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

    def __init__(self, dsn: str, dimension: int, provider: str = "mock") -> None:
        self._dsn = dsn
        self._dimension = dimension
        self._provider = provider
        logging.info("PgVectorStore MS6: Skipping table validation for dual-write test")

    @property
    def dimension(self) -> int:
        return self._dimension

    def persist(self, records: list[VectorRecord]) -> None:
        self.add(records)
        logging.debug("PgVectorStore.persist: added %d records", len(records))

    def add(self, records: Iterable[VectorRecord]) -> None:
        """MS6 Dual-write: vectors + vector_chunks"""
        vectors_sql = sql.SQL("""
            INSERT INTO {schema}.vectors 
            (vector, ingestion_id, chunk_id, chunk_index, chunk_strategy, 
             chunk_text, source_metadata, provider)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """).format(schema=sql.Identifier(self.SCHEMA))

        chunks_sql = sql.SQL("""
            INSERT INTO {schema}.vector_chunks 
            (vector, ingestion_id, chunk_id, chunk_index, chunk_strategy, 
             chunk_text, source_metadata, provider, document_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """).format(schema=sql.Identifier(self.SCHEMA))

        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                for record in records:
                    cur.execute(vectors_sql, (
                        record.vector, record.metadata.ingestion_id,
                        record.metadata.chunk_id, record.metadata.chunk_index,
                        record.metadata.chunk_strategy, record.metadata.chunk_text,
                        Jsonb(record.metadata.source_metadata or {}),
                        record.metadata.provider or self._provider,
                    ))
                    if record.metadata.document_id:
                        cur.execute(chunks_sql, (
                            record.vector, record.metadata.ingestion_id,
                            record.metadata.chunk_id, record.metadata.chunk_index,
                            record.metadata.chunk_strategy, record.metadata.chunk_text,
                            Jsonb(record.metadata.source_metadata or {}),
                            record.metadata.provider or self._provider,
                            record.metadata.document_id,
                        ))
        logging.info(f"MS6 DUAL-WRITE: {len(records)} vectors + chunks complete")

    def similarity_search(
        self,
        query_vector: Sequence[float],
        k: int,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[VectorRecord]:
        """
        Search vector_chunks with optional metadata filtering.

        metadata_filter supports:
            {"source_type": "code"}              → equality
            {"source_type": {"ne": "code"}}      → not equal (also matches NULL)
            {"doc_type": {"in": ["file","pdf"]}} → IN list
        """
        if metadata_filter:
            conditions = []
            filter_values = []

            for key, value in metadata_filter.items():
                if isinstance(value, dict):
                    operator = list(value.keys())[0]
                    operand = list(value.values())[0]

                    if operator == "ne":
                        conditions.append(
                            sql.SQL(
                                "(source_metadata->>{key} IS NULL "
                                "OR source_metadata->>{key} != {val})"
                            ).format(
                                key=sql.Literal(key),
                                val=sql.Placeholder(),
                            )
                        )
                        filter_values.append(operand)

                    elif operator == "in":
                        placeholders = sql.SQL(", ").join(
                            sql.Placeholder() for _ in operand
                        )
                        conditions.append(
                            sql.SQL(
                                "source_metadata->>{key} IN ({vals})"
                            ).format(
                                key=sql.Literal(key),
                                vals=placeholders,
                            )
                        )
                        filter_values.extend(operand)

                else:
                    # Simple equality
                    conditions.append(
                        sql.SQL("source_metadata->>{key} = {val}").format(
                            key=sql.Literal(key),
                            val=sql.Placeholder(),
                        )
                    )
                    filter_values.append(value)

            where_clause = sql.SQL(" AND ").join(conditions)
            search_sql = sql.SQL("""
                SELECT vector, ingestion_id, chunk_id, chunk_index, chunk_strategy,
                       chunk_text, source_metadata, provider, document_id
                FROM {schema}.vector_chunks
                WHERE {where}
                ORDER BY vector <-> ({qvec}::vector)
                LIMIT {limit}
            """).format(
                schema=sql.Identifier(self.SCHEMA),
                where=where_clause,
                qvec=sql.Placeholder(),
                limit=sql.Placeholder(),
            )
            params = filter_values + [query_vector, k]

        else:
            search_sql = sql.SQL("""
                SELECT vector, ingestion_id, chunk_id, chunk_index, chunk_strategy,
                       chunk_text, source_metadata, provider, document_id
                FROM {schema}.vector_chunks
                ORDER BY vector <-> ({qvec}::vector)
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
                cur.execute(search_sql, params)
                for row in cur.fetchall():
                    (vector, ingestion_id, chunk_id, chunk_index, chunk_strategy,
                     chunk_text, source_metadata, provider, document_id) = row
                    metadata = VectorMetadata(
                        ingestion_id=ingestion_id,
                        chunk_id=chunk_id,
                        chunk_index=chunk_index,
                        chunk_strategy=chunk_strategy,
                        chunk_text=chunk_text,
                        source_metadata=source_metadata,
                        provider=provider,
                        document_id=document_id,
                    )
                    results.append(VectorRecord(vector=vector, metadata=metadata))
        return results

    def delete_by_ingestion_id(self, ingestion_id: str) -> None:
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

    def get_chunks_by_document_id(self, document_id: str, k: int = 3) -> List[VectorRecord]:
        """Fetch chunks for a specific document_id — no vector similarity needed."""
        search_sql = sql.SQL("""
            SELECT vector, ingestion_id, chunk_id, chunk_index, chunk_strategy,
                chunk_text, source_metadata, provider, document_id
            FROM {schema}.vector_chunks
            WHERE document_id = {doc_id}
            LIMIT {limit}
        """).format(
            schema=sql.Identifier(self.SCHEMA),
            doc_id=sql.Placeholder(),
            limit=sql.Placeholder(),
        )
        results: List[VectorRecord] = []
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(search_sql, (document_id, k))
                for row in cur.fetchall():
                    (vector, ingestion_id, chunk_id, chunk_index, chunk_strategy,
                    chunk_text, source_metadata, provider, document_id) = row
                    metadata = VectorMetadata(
                        ingestion_id=ingestion_id,
                        chunk_id=chunk_id,
                        chunk_index=chunk_index,
                        chunk_strategy=chunk_strategy,
                        chunk_text=chunk_text,
                        source_metadata=source_metadata,
                        provider=provider,
                        document_id=document_id,
                    )
                    results.append(VectorRecord(vector=vector, metadata=metadata))
        return results
