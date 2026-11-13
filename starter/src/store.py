"""Persistent exact cosine search using PostgreSQL and pgvector."""
from __future__ import annotations

import json
import math
import re
from typing import Any

import psycopg
from psycopg import sql

from .models import Chunk


class PgVectorStore:
    TABLE = "day06_chunks"
    FILTER_COLUMNS = {"document_id", "source", "page", "unit_id"}
    FILTER_METADATA = {
        "chapter", "collection", "version", "sequence_in_chapter", "sequence_in_source"
    }

    def __init__(
        self, database_url: str, dimensions: int, table_name: str = "day06_chunks"
    ) -> None:
        if not database_url.strip():
            raise ValueError("database_url must not be empty")
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", table_name):
            raise ValueError("table_name must be a safe lower-case PostgreSQL identifier")
        self.database_url = database_url
        self.dimensions = dimensions
        self.TABLE = table_name

    def create_schema(self) -> None:
        statement = sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {table} (
                strategy text NOT NULL,
                chunk_id text NOT NULL,
                document_id text NOT NULL,
                source text NOT NULL,
                page integer,
                unit_id text NOT NULL,
                sequence integer NOT NULL,
                char_start integer NOT NULL,
                char_end integer NOT NULL,
                text text NOT NULL,
                metadata jsonb NOT NULL,
                embedding vector({dimensions}) NOT NULL,
                PRIMARY KEY (strategy, chunk_id),
                CHECK (char_start >= 0 AND char_end > char_start)
            )
            """
        ).format(table=sql.Identifier(self.TABLE), dimensions=sql.Literal(self.dimensions))
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(statement)
                cursor.execute(
                    """
                    SELECT format_type(a.atttypid, a.atttypmod)
                    FROM pg_attribute a
                    WHERE a.attrelid = %s::regclass AND a.attname = 'embedding'
                    """,
                    (self.TABLE,),
                )
                vector_type = cursor.fetchone()
                if not vector_type or vector_type[0] != f"vector({self.dimensions})":
                    raise RuntimeError(
                        f"Existing {self.TABLE} embedding column is {vector_type}; "
                        f"expected vector({self.dimensions})"
                    )

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Upsert stable IDs and remove stale chunks in the affected documents.

        When re-ingesting changed source documents, remove obsolete chunks too.
        """
        if not strategy.strip():
            raise ValueError("strategy must not be empty")
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have equal lengths")
        if not chunks:
            return
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise ValueError(f"Expected vector dimension {self.dimensions}")
            if not all(math.isfinite(value) for value in vector):
                raise ValueError("Vector contains a non-finite value")
        chunk_ids_by_document: dict[str, list[str]] = {}
        for chunk in chunks:
            chunk_ids_by_document.setdefault(chunk.document_id, []).append(chunk.chunk_id)
        rows = [
            (
                strategy,
                chunk.chunk_id,
                chunk.document_id,
                chunk.source,
                chunk.page,
                chunk.unit_id,
                chunk.sequence,
                chunk.char_start,
                chunk.char_end,
                chunk.text,
                json.dumps(chunk.metadata, ensure_ascii=False),
                self._vector_literal(vector),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    sql.SQL(
                        """
                        INSERT INTO {table} (
                            strategy, chunk_id, document_id, source, page, unit_id,
                            sequence, char_start, char_end, text, metadata, embedding
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector
                        )
                        ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                            document_id = EXCLUDED.document_id,
                            source = EXCLUDED.source,
                            page = EXCLUDED.page,
                            unit_id = EXCLUDED.unit_id,
                            sequence = EXCLUDED.sequence,
                            char_start = EXCLUDED.char_start,
                            char_end = EXCLUDED.char_end,
                            text = EXCLUDED.text,
                            metadata = EXCLUDED.metadata,
                            embedding = EXCLUDED.embedding
                        """
                    ).format(table=sql.Identifier(self.TABLE)),
                    rows,
                )
                for document_id, chunk_ids in chunk_ids_by_document.items():
                    cursor.execute(
                        sql.SQL(
                            "DELETE FROM {table} "
                            "WHERE strategy = %s AND document_id = %s "
                            "AND NOT (chunk_id = ANY(%s))"
                        ).format(table=sql.Identifier(self.TABLE)),
                        (strategy, document_id, chunk_ids),
                    )

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Apply allow-listed filters and rank with exact cosine distance.

        Return chunk ID, text, score and metadata. Parameterize user-supplied values.
        """
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if len(query_vector) != self.dimensions or not all(
            math.isfinite(value) for value in query_vector
        ):
            raise ValueError("Query vector has invalid dimensions or values")
        conditions = [sql.SQL("strategy = %s")]
        condition_parameters: list[Any] = [strategy]
        for key, value in (filters or {}).items():
            if key in self.FILTER_COLUMNS:
                conditions.append(sql.SQL("{} = %s").format(sql.Identifier(key)))
                condition_parameters.append(value)
            elif key in self.FILTER_METADATA:
                conditions.append(sql.SQL("metadata ->> %s = %s"))
                condition_parameters.extend([key, str(value)])
            else:
                raise ValueError(f"Unsupported metadata filter: {key}")
        vector_literal = self._vector_literal(query_vector)
        # PostgreSQL binds placeholders in textual order: score vector first,
        # then WHERE parameters, ORDER BY vector, and LIMIT.
        parameters = [vector_literal, *condition_parameters, vector_literal, top_k]
        query = sql.SQL(
            """
            SELECT chunk_id, text, 1 - (embedding <=> %s::vector) AS score,
                   document_id, source, page, unit_id, sequence,
                   char_start, char_end, metadata
            FROM {table}
            WHERE {conditions}
            ORDER BY embedding <=> %s::vector, chunk_id
            LIMIT %s
            """
        ).format(
            table=sql.Identifier(self.TABLE),
            conditions=sql.SQL(" AND ").join(conditions),
        )
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, parameters)
                rows = cursor.fetchall()
        return [
            {
                "rank": rank,
                "chunk_id": row[0],
                "text": row[1],
                "score": float(row[2]),
                "document_id": row[3],
                "source": row[4],
                "page": row[5],
                "unit_id": row[6],
                "sequence": row[7],
                "char_start": row[8],
                "char_end": row[9],
                "metadata": row[10],
            }
            for rank, row in enumerate(rows, start=1)
        ]

    def count(self, strategy: str | None = None) -> int:
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                if strategy is None:
                    cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(self.TABLE)))
                else:
                    cursor.execute(
                        sql.SQL("SELECT count(*) FROM {} WHERE strategy = %s").format(
                            sql.Identifier(self.TABLE)
                        ),
                        (strategy,),
                    )
                return int(cursor.fetchone()[0])

    @staticmethod
    def _vector_literal(vector: list[float]) -> str:
        return "[" + ",".join(format(value, ".9g") for value in vector) + "]"
