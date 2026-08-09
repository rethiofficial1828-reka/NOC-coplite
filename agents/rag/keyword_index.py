"""
Keyword Index Module.

Implements an enterprise-grade BM25 sparse keyword search index with term frequency normalization,
document length scaling, metadata field filtering, and term weighting.
"""

import math
import re
import threading
from typing import Any, Dict, List, Optional, Set

from agents.core.logger import get_agent_logger
from agents.rag.interfaces import IKeywordIndex
from agents.rag.models import (
    DocumentChunk,
    RetrievalResult,
    RetrievalStrategy,
    SearchMetadata,
)

logger = get_agent_logger("KeywordIndex")


class KeywordIndex(IKeywordIndex):
    """
    Enterprise BM25 sparse keyword search engine.

    Formulas:
        IDF(q) = log( (N - n(q) + 0.5) / (n(q) + 0.5) + 1 )
        Score(D, Q) = sum_{q in Q} IDF(q) * [ (f(q, D) * (k1 + 1)) / (f(q, D) + k1 * (1 - b + b * (|D| / avgdl))) ]
    """

    STOPWORDS: Set[str] = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he",
        "in", "is", "it", "its", "of", "on", "that", "the", "to", "was", "were",
        "will", "with", "or", "if", "this", "these", "those", "can", "should", "not"
    }

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._lock = threading.RLock()

        # Storage
        self._chunks: Dict[str, DocumentChunk] = {}
        # Inverted index: word -> dict of {chunk_id: term_freq}
        self._inverted_index: Dict[str, Dict[str, int]] = {}
        # Document lengths: chunk_id -> int
        self._doc_lengths: Dict[str, int] = {}
        self._avg_doc_len: float = 0.0

    def index_chunks(self, chunks: List[DocumentChunk]) -> None:
        """
        Index a batch of DocumentChunk instances into the BM25 inverted index.
        """
        if not chunks:
            return

        with self._lock:
            for chunk in chunks:
                self._chunks[chunk.chunk_id] = chunk

                tokens = self._tokenize(chunk.content)
                self._doc_lengths[chunk.chunk_id] = len(tokens)

                term_counts: Dict[str, int] = {}
                for t in tokens:
                    term_counts[t] = term_counts.get(t, 0) + 1

                for term, count in term_counts.items():
                    if term not in self._inverted_index:
                        self._inverted_index[term] = {}
                    self._inverted_index[term][chunk.chunk_id] = count

            # Update avg document length
            total_len = sum(self._doc_lengths.values())
            total_docs = len(self._chunks)
            self._avg_doc_len = (total_len / total_docs) if total_docs > 0 else 0.0

        logger.info(f"Indexed {len(chunks)} chunk(s) into BM25 KeywordIndex (total={len(self._chunks)}).")

    def search(
        self,
        query: str,
        top_k: int = 5,
        search_metadata: Optional[SearchMetadata] = None,
    ) -> List[RetrievalResult]:
        """
        Execute BM25 keyword search for query text.
        """
        query_tokens = self._tokenize(query)
        if not query_tokens or not self._chunks:
            return []

        with self._lock:
            total_docs = len(self._chunks)
            scores: Dict[str, float] = {}

            for token in set(query_tokens):
                postings = self._inverted_index.get(token, {})
                if not postings:
                    continue

                doc_freq = len(postings)
                # BM25 IDF
                idf = math.log((total_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)

                for chunk_id, tf in postings.items():
                    doc_len = self._doc_lengths.get(chunk_id, 1)
                    num = tf * (self._k1 + 1.0)
                    den = tf + self._k1 * (1.0 - self._b + self._b * (doc_len / max(1.0, self._avg_doc_len)))
                    bm25_term = idf * (num / den)

                    scores[chunk_id] = scores.get(chunk_id, 0.0) + bm25_term

            if not scores:
                return []

            results: List[RetrievalResult] = []
            max_score = max(scores.values()) if scores.values() else 1.0

            for chunk_id, raw_score in scores.items():
                chunk = self._chunks[chunk_id]

                # Metadata filter check
                if search_metadata and not self._matches_filter(chunk, search_metadata):
                    continue

                norm_score = (raw_score / max_score) if max_score > 0 else 0.0

                results.append(
                    RetrievalResult(
                        chunk=chunk,
                        score=norm_score,
                        dense_score=0.0,
                        sparse_score=norm_score,
                        rerank_score=norm_score,
                        retrieval_strategy=RetrievalStrategy.SPARSE_BM25,
                    )
                )

            # Sort descending
            results.sort(key=lambda r: r.score, reverse=True)

            for i, res in enumerate(results[:top_k]):
                res.rank = i + 1

            return results[:top_k]

    def clear(self) -> None:
        """Clear all indexed data."""
        with self._lock:
            self._chunks.clear()
            self._inverted_index.clear()
            self._doc_lengths.clear()
            self._avg_doc_len = 0.0

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> List[str]:
        """Convert text into cleaned alphanumeric token terms."""
        cleaned = text.lower().replace("-", " ").replace("_", " ")
        words = re.findall(r"\b[a-z0-9]{2,}\b", cleaned)
        return [w for w in words if w not in self.STOPWORDS]

    @staticmethod
    def _matches_filter(chunk: DocumentChunk, filter_meta: SearchMetadata) -> bool:
        if filter_meta.device_id:
            dev = filter_meta.device_id.lower()
            if dev not in chunk.content.lower() and dev not in str(chunk.metadata).lower():
                return False

        if filter_meta.tags:
            chunk_tags = set(chunk.tags)
            if not any(t in chunk_tags for t in filter_meta.tags):
                return False

        return True
