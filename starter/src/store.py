from __future__ import annotations

import json
import math
from typing import Any

import psycopg
from psycopg import sql
from .models import Chunk


class PgVectorStore:
    ALLOWED_FILTERS = frozenset({"section", "source", "document_id", "page"})

    def __init__(self, database_url: str, dimensions: int) -> None:
        if not database_url:
            raise ValueError("Missing DATABASE_URL")
        if not isinstance(dimensions, int) or dimensions <= 0 or dimensions > 2000:
            raise ValueError("Invalid pgvector dimensions (must be between 1 and 2000)")
        self.database_url = database_url
        self.dimensions = dimensions

    @staticmethod
    def _vector_literal(vector: list[float], dimensions: int) -> str:
        if len(vector) != dimensions:
            raise ValueError(f"Vector length {len(vector)} does not match {dimensions}")
        if not all(math.isfinite(float(x)) for x in vector):
            raise ValueError("Vector contains NaN or Infinity")
        return "[" + ",".join(format(float(x), ".10g") for x in vector) + "]"

    def create_schema(self) -> None:
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(sql.SQL("""
                    CREATE TABLE IF NOT EXISTS lab_document_chunks (
                        strategy TEXT NOT NULL,
                        chunk_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        page INTEGER NOT NULL,
                        content TEXT NOT NULL,
                        metadata JSONB NOT NULL,
                        embedding VECTOR({}) NOT NULL,
                        PRIMARY KEY (strategy, chunk_id)
                    )
                """).format(sql.SQL(str(self.dimensions))))
                cur.execute("SELECT atttypmod FROM pg_attribute WHERE attrelid = 'lab_document_chunks'::regclass AND attname = 'embedding'")
                actual = cur.fetchone()
                if not actual or actual[0] != self.dimensions:
                    raise ValueError("Existing vector table uses a different dimension; use the same embedding model")
                cur.execute("CREATE INDEX IF NOT EXISTS lab_chunks_strategy_section_idx ON lab_document_chunks (strategy, (metadata->>'section'))")
                cur.execute("CREATE INDEX IF NOT EXISTS lab_chunks_document_idx ON lab_document_chunks (strategy, document_id)")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Atomically replace a strategy's corpus, removing stale chunks on rerun."""
        if strategy not in {"A", "B"}:
            raise ValueError("Only A and B are stored; C reuses B with filters")
        if len(chunks) != len(vectors):
            raise ValueError("One vector required for every chunk")
        if not chunks:
            raise ValueError("Refusing to replace collection with zero chunks")
        ids = [c.chunk_id for c in chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate chunk IDs in this ingestion")
        params = []
        for chunk, vector in zip(chunks, vectors):
            meta = {**chunk.metadata, "source": chunk.source,
                    "document_id": chunk.document_id, "page": chunk.page}
            if not isinstance(meta.get("section"), str):
                raise ValueError(f"Missing scalar section on {chunk.chunk_id}")
            params.append((strategy, chunk.chunk_id, chunk.document_id, chunk.source,
                           chunk.page, chunk.text, json.dumps(meta, ensure_ascii=False),
                           self._vector_literal(vector, self.dimensions)))
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                # Keep other strategies intact. Transaction rollback preserves previous
                # collection if insertion fails.
                cur.execute("DELETE FROM lab_document_chunks WHERE strategy = %s", (strategy,))
                cur.executemany("""
                    INSERT INTO lab_document_chunks
                    (strategy, chunk_id, document_id, source, page, content, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector)
                    ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                      document_id=EXCLUDED.document_id, source=EXCLUDED.source,
                      page=EXCLUDED.page, content=EXCLUDED.content,
                      metadata=EXCLUDED.metadata, embedding=EXCLUDED.embedding
                """, params)

    def count(self, strategy: str) -> int:
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM lab_document_chunks WHERE strategy=%s", ("B" if strategy == "C" else strategy,))
                return int(cur.fetchone()[0])

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if strategy not in {"A", "B", "C"}:
            raise ValueError("Unknown retrieval strategy")
        if top_k < 1 or top_k > 100:
            raise ValueError("top_k must be 1..100")
        literal = self._vector_literal(query_vector, self.dimensions)
        where = ["strategy = %s"]
        params: list[Any] = ["B" if strategy == "C" else strategy]
        for key, value in (filters or {}).items():
            if key not in self.ALLOWED_FILTERS:
                raise ValueError(f"Unsupported metadata filter: {key}")
            if not isinstance(value, (str, int)):
                raise ValueError(f"Filter {key} must be a string or integer")
            # Only static keys from whitelist appear in the query (via Identifier).
            where.append(sql.SQL("metadata ->> {} = %s").format(sql.Literal(key)))
            params.append(str(value))
        statement = sql.SQL("""
            SELECT chunk_id, document_id, source, page, content, metadata,
                   1 - (embedding <=> %s::vector) AS score
            FROM lab_document_chunks
            WHERE {conditions}
            ORDER BY embedding <=> %s::vector, chunk_id
            LIMIT %s
        """).format(conditions=sql.SQL(" AND ").join(
            sql.SQL(part) if isinstance(part, str) else part for part in where
        ))
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(statement, [literal, *params, literal, top_k])
                rows = cur.fetchall()
        return [{"chunk_id": row[0], "document_id": row[1], "source": row[2],
                 "page": row[3], "text": row[4], "metadata": row[5],
                 "score": float(row[6])} for row in rows]
