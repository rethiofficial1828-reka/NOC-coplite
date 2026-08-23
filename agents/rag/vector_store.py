"""
Vector Store Module.

Implements SQLiteVectorStore — a production-grade, thread-safe persistent vector store using SQLite
and NumPy for vector similarity calculations and metadata filtering.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from agents.core.logger import get_agent_logger
from agents.rag.interfaces import IVectorStore
from agents.rag.models import (
    ChunkingStrategy,
    DocumentChunk,
    RetrievalResult,
    RetrievalStrategy,
    SearchMetadata,
)

logger = get_agent_logger("VectorStore")


class SQLiteVectorStore(IVectorStore):
    """
    Thread-safe persistent vector store implementation using SQLite + NumPy cosine similarity.
    Supports insert, update, batch_insert, delete, metadata filtering, and persistent disk storage.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()

        if db_path is not None:
            self._db_path = db_path
        else:
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            self._db_path = os.path.join(project_root, "data", "vector_store.db")

        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._ensure_schema()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS vector_chunks (
                        chunk_id TEXT PRIMARY KEY,
                        parent_doc_id TEXT NOT NULL,
                        chunk_index INTEGER NOT NULL,
                        content TEXT NOT NULL,
                        token_count INTEGER DEFAULT 0,
                        heading_hierarchy TEXT,
                        chunking_strategy TEXT,
                        source TEXT,
                        tags TEXT,
                        metadata TEXT,
                        vector_blob BLOB NOT NULL,
                        dimension INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_vector_doc ON vector_chunks(parent_doc_id)"
                )
                conn.commit()

    # ------------------------------------------------------------------
    # IVectorStore API Implementation
    # ------------------------------------------------------------------

    def insert(self, chunk: DocumentChunk, vector: List[float]) -> None:
        """Insert a single DocumentChunk and its embedding vector into the database."""
        self.batch_insert([chunk], [vector])

    def batch_insert(
        self, chunks: List[DocumentChunk], vectors: List[List[float]]
    ) -> None:
        """Insert a batch of DocumentChunk instances and vector float arrays."""
        if len(chunks) != len(vectors):
            raise ValueError("Chunks and vectors lists must have identical length.")

        if not chunks:
            return

        rows: List[Tuple[str, str, int, str, int, str, str, str, str, str, bytes, int]] = []
        for chunk, vec in zip(chunks, vectors):
            vec_arr = np.array(vec, dtype=np.float32)
            blob = vec_arr.tobytes()
            dimension = len(vec)

            rows.append(
                (
                    chunk.chunk_id,
                    chunk.parent_doc_id,
                    chunk.chunk_index,
                    chunk.content,
                    chunk.token_count,
                    json.dumps(chunk.heading_hierarchy),
                    chunk.chunking_strategy.value if hasattr(chunk.chunking_strategy, "value") else str(chunk.chunking_strategy),
                    chunk.source,
                    json.dumps(chunk.tags),
                    json.dumps(chunk.metadata),
                    blob,
                    dimension,
                )
            )

        with self._lock:
            with self._get_connection() as conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO vector_chunks (
                        chunk_id, parent_doc_id, chunk_index, content, token_count,
                        heading_hierarchy, chunking_strategy, source, tags, metadata,
                        vector_blob, dimension
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.commit()

        logger.info(f"Inserted {len(chunks)} vector chunk(s) into SQLiteVectorStore.")

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        search_metadata: Optional[SearchMetadata] = None,
    ) -> List[RetrievalResult]:
        """
        Search for top_k vector matches using NumPy cosine similarity and metadata filters.
        """
        if not query_vector:
            return []

        q_vec = np.array(query_vector, dtype=np.float32)
        q_norm = float(np.linalg.norm(q_vec))
        if q_norm == 0.0:
            return []

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT chunk_id, parent_doc_id, chunk_index, content, token_count, heading_hierarchy, chunking_strategy, source, tags, metadata, vector_blob, dimension FROM vector_chunks"
                )
                rows = cursor.fetchall()

        if not rows:
            return []

        results: List[RetrievalResult] = []

        for row in rows:
            blob = row["vector_blob"]
            vec_arr = np.frombuffer(blob, dtype=np.float32)

            if len(vec_arr) != len(q_vec):
                continue

            v_norm = float(np.linalg.norm(vec_arr))
            similarity = float(np.dot(q_vec, vec_arr) / (q_norm * v_norm)) if v_norm > 0 else 0.0

            # Construct DocumentChunk
            chunk = DocumentChunk(
                chunk_id=row["chunk_id"],
                parent_doc_id=row["parent_doc_id"],
                chunk_index=row["chunk_index"],
                content=row["content"],
                token_count=row["token_count"],
                heading_hierarchy=json.loads(row["heading_hierarchy"] or "[]"),
                chunking_strategy=ChunkingStrategy(row["chunking_strategy"]) if row["chunking_strategy"] in [s.value for s in ChunkingStrategy] else ChunkingStrategy.FIXED_SIZE,
                source=row["source"] or "",
                tags=json.loads(row["tags"] or "[]"),
                metadata=json.loads(row["metadata"] or "{}"),
            )

            # Apply Metadata Filter if provided
            if search_metadata:
                if not self._matches_filter(chunk, search_metadata):
                    continue

            results.append(
                RetrievalResult(
                    chunk=chunk,
                    score=similarity,
                    dense_score=similarity,
                    sparse_score=0.0,
                    rerank_score=similarity,
                    retrieval_strategy=RetrievalStrategy.DENSE_ONLY,
                )
            )

        # Sort descending by score
        results.sort(key=lambda r: r.score, reverse=True)

        for i, res in enumerate(results[:top_k]):
            res.rank = i + 1

        return results[:top_k]

    def delete(self, chunk_id: str) -> bool:
        """Delete a vector chunk by ID."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM vector_chunks WHERE chunk_id = ?", (chunk_id,))
                deleted = cursor.rowcount > 0
                conn.commit()
        return deleted

    def count(self) -> int:
        """Return aggregate count of vector chunks in database."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as cnt FROM vector_chunks")
                row = cursor.fetchone()
                return int(row["cnt"]) if row else 0

    def clear(self) -> None:
        """Clear all stored vectors from database."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM vector_chunks")
                conn.commit()

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_filter(chunk: DocumentChunk, filter_meta: SearchMetadata) -> bool:
        """Check whether chunk matches SearchMetadata filters."""
        if filter_meta.device_id:
            dev = filter_meta.device_id.lower()
            if dev not in chunk.content.lower() and dev not in str(chunk.metadata).lower():
                return False

        if filter_meta.tags:
            chunk_tags = set(chunk.tags)
            if not any(t in chunk_tags for t in filter_meta.tags):
                return False

        return True


VectorStore = SQLiteVectorStore
