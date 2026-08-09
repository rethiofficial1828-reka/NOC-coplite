"""
Hybrid Retriever Module.

Implements HybridRetriever — combining Dense Vector Search + BM25 Sparse Search
using Reciprocal Rank Fusion (RRF) and Device/Topology/Incident-aware metadata filtering.
"""

from typing import Dict, List, Optional, Set

from agents.core.logger import get_agent_logger
from agents.rag.interfaces import IEmbeddingProvider, IHybridRetriever, IKeywordIndex, IVectorStore
from agents.rag.models import (
    DocumentChunk,
    RetrievalResult,
    RetrievalStrategy,
    SearchMetadata,
)

logger = get_agent_logger("HybridRetriever")


class HybridRetriever(IHybridRetriever):
    """
    Enterprise Hybrid Retrieval engine combining Dense Vector Search and BM25 Sparse Search
    via Reciprocal Rank Fusion (RRF).
    """

    def __init__(
        self,
        vector_store: IVectorStore,
        keyword_index: IKeywordIndex,
        embedding_provider: IEmbeddingProvider,
        rrf_k: int = 60,
        dense_weight: float = 0.5,
        sparse_weight: float = 0.5,
    ) -> None:
        self._vector_store = vector_store
        self._keyword_index = keyword_index
        self._embedding_provider = embedding_provider
        self._rrf_k = rrf_k
        self._dense_weight = dense_weight
        self._sparse_weight = sparse_weight

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        search_metadata: Optional[SearchMetadata] = None,
    ) -> List[RetrievalResult]:
        """
        Perform hybrid candidate retrieval.

        Steps:
            1. Dense vector search via VectorStore.
            2. Sparse BM25 search via KeywordIndex.
            3. Apply Reciprocal Rank Fusion (RRF).
            4. Return combined top_k ranked results.
        """
        if not query.strip():
            return []

        # Step 1: Dense Retrieval
        dense_results: List[RetrievalResult] = []
        try:
            q_vector = self._embedding_provider.embed_text(query)
            dense_results = self._vector_store.search(
                query_vector=q_vector,
                top_k=top_k * 2,
                search_metadata=search_metadata,
            )
        except Exception as e:
            logger.error(f"Dense vector retrieval error: {e}")

        # Step 2: Sparse BM25 Retrieval
        sparse_results: List[RetrievalResult] = []
        try:
            sparse_results = self._keyword_index.search(
                query=query,
                top_k=top_k * 2,
                search_metadata=search_metadata,
            )
        except Exception as e:
            logger.error(f"Sparse BM25 retrieval error: {e}")

        # Step 3: Reciprocal Rank Fusion (RRF)
        fused = self._reciprocal_rank_fusion(
            dense_results=dense_results,
            sparse_results=sparse_results,
            top_k=top_k,
        )

        logger.info(
            f"HybridRetriever retrieved {len(fused)} candidate chunk(s) "
            f"(dense={len(dense_results)}, sparse={len(sparse_results)})."
        )
        return fused

    # ------------------------------------------------------------------
    # RRF Fusion Logic
    # ------------------------------------------------------------------

    def _reciprocal_rank_fusion(
        self,
        dense_results: List[RetrievalResult],
        sparse_results: List[RetrievalResult],
        top_k: int,
    ) -> List[RetrievalResult]:
        """
        Reciprocal Rank Fusion (RRF) algorithm:
            RRF_Score(d) = w_dense * (1.0 / (k + rank_dense(d))) + w_sparse * (1.0 / (k + rank_sparse(d)))
        """
        rrf_scores: Dict[str, float] = {}
        dense_scores_map: Dict[str, float] = {}
        sparse_scores_map: Dict[str, float] = {}
        chunks_map: Dict[str, DocumentChunk] = {}

        # Process Dense Ranks
        for rank, res in enumerate(dense_results, start=1):
            cid = res.chunk.chunk_id
            chunks_map[cid] = res.chunk
            dense_scores_map[cid] = res.score
            rrf = self._dense_weight * (1.0 / (self._rrf_k + rank))
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + rrf

        # Process Sparse Ranks
        for rank, res in enumerate(sparse_results, start=1):
            cid = res.chunk.chunk_id
            chunks_map[cid] = res.chunk
            sparse_scores_map[cid] = res.score
            rrf = self._sparse_weight * (1.0 / (self._rrf_k + rank))
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + rrf

        if not rrf_scores:
            return []

        # Normalize fused RRF scores
        max_rrf = max(rrf_scores.values()) if rrf_scores.values() else 1.0

        fused_results: List[RetrievalResult] = []
        for cid, raw_rrf in rrf_scores.items():
            norm_score = raw_rrf / max_rrf if max_rrf > 0 else 0.0
            chunk = chunks_map[cid]

            fused_results.append(
                RetrievalResult(
                    chunk=chunk,
                    score=norm_score,
                    dense_score=dense_scores_map.get(cid, 0.0),
                    sparse_score=sparse_scores_map.get(cid, 0.0),
                    rerank_score=norm_score,
                    retrieval_strategy=RetrievalStrategy.HYBRID_RRF,
                )
            )

        # Sort descending by RRF score
        fused_results.sort(key=lambda r: r.score, reverse=True)

        for i, res in enumerate(fused_results[:top_k]):
            res.rank = i + 1

        return fused_results[:top_k]
