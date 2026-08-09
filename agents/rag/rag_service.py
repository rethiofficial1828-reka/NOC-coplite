"""
RAG Service Module.

Implements RAGService — the central business logic orchestrator for the Enterprise RAG/CAG Intelligence Subsystem.
Workflow:
    Query -> CAG Context Builder -> Hybrid Retrieval -> Reranker -> Context Quality -> Prompt Assembly -> LLM -> Citations -> RAGResult
"""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.rag.context_builder import ContextBuilder
from agents.rag.context_quality import ContextQualityEvaluator
from agents.rag.embedding_factory import EmbeddingProviderFactory
from agents.rag.hybrid_retriever import HybridRetriever
from agents.rag.index_manager import IndexManager
from agents.rag.keyword_index import KeywordIndex
from agents.rag.prompt_assembler import PromptAssembler
from agents.rag.reranker import Reranker
from agents.rag.retrieval_cache import RetrievalCache
from agents.rag.vector_store import SQLiteVectorStore
from agents.rag.models import (
    CAGContext,
    Citation,
    ContextPackage,
    ContextQuality,
    PromptPackage,
    RAGResult,
    RetrievalResult,
    SearchMetadata,
)

logger = get_agent_logger("RAGService")


class RAGService:
    """
    Central orchestration service managing Context Building, Hybrid Retrieval, Reranking,
    Prompt Assembly, Quality Evaluation, and Citation Generation.
    """

    def __init__(
        self,
        context_builder: Optional[ContextBuilder] = None,
        hybrid_retriever: Optional[HybridRetriever] = None,
        reranker: Optional[Reranker] = None,
        quality_evaluator: Optional[ContextQualityEvaluator] = None,
        prompt_assembler: Optional[PromptAssembler] = None,
        cache: Optional[RetrievalCache] = None,
        vector_store: Optional[SQLiteVectorStore] = None,
        keyword_index: Optional[KeywordIndex] = None,
    ) -> None:
        self._context_builder = context_builder or ContextBuilder()
        self._vector_store = vector_store or SQLiteVectorStore()
        self._keyword_index = keyword_index or KeywordIndex()
        self._embedding_provider = EmbeddingProviderFactory.create_provider("tfidf")

        self._hybrid_retriever = hybrid_retriever or HybridRetriever(
            vector_store=self._vector_store,
            keyword_index=self._keyword_index,
            embedding_provider=self._embedding_provider,
        )

        self._reranker = reranker or Reranker()
        self._quality_evaluator = quality_evaluator or ContextQualityEvaluator()
        self._prompt_assembler = prompt_assembler or PromptAssembler()
        self._cache = cache or RetrievalCache()
        self._index_manager = IndexManager(
            vector_store=self._vector_store,
            keyword_index=self._keyword_index,
            embedding_provider=self._embedding_provider,
        )

    @property
    def index_manager(self) -> IndexManager:
        """Index manager instance for adding enterprise documentation."""
        return self._index_manager

    def build_context_package(
        self,
        query: str,
        device_id: str = "",
        execution_context: Optional[Any] = None,
        top_k: int = 5,
    ) -> ContextPackage:
        """
        Build a complete ContextPackage containing CAG operational state, hybrid retrieved chunks,
        reranked candidates, citations, and quality score.

        Args:
            query: Operator query string.
            device_id: Monitored device ID.
            execution_context: ExecutionContext object from agent framework.
            top_k: Max candidate chunks to retrieve.

        Returns:
            ContextPackage instance.
        """
        start_time = time.time()

        # Step 1: CAG Context Building
        cag_context = self._context_builder.build_context(
            query=query, device_id=device_id, execution_context=execution_context
        )

        # Step 2: Hybrid Search with Cache
        cached_candidates = self._cache.get(query, {"device_id": cag_context.device_id})
        if cached_candidates is not None:
            candidates = cached_candidates
        else:
            search_meta = SearchMetadata(device_id=cag_context.device_id if cag_context.device_id != "unknown" else None)
            candidates = self._hybrid_retriever.retrieve(
                query=query or cag_context.device_id, top_k=top_k * 2, search_metadata=search_meta
            )
            self._cache.set(query, candidates, {"device_id": cag_context.device_id})

        # Step 3: Reranking
        ranked_results = self._reranker.rerank(
            query=query, candidates=candidates, context=cag_context, top_k=top_k
        )

        # Step 4: Quality Evaluation
        quality = self._quality_evaluator.evaluate_quality(cag_context, ranked_results)

        # Step 5: Citation Generation
        from agents.rag.citations import CitationGenerator
        citations = CitationGenerator.generate_citations(ranked_results)

        package = ContextPackage(
            cag_context=cag_context,
            retrieved_results=ranked_results,
            citations=citations,
            quality=quality,
        )

        elapsed = (time.time() - start_time) * 1000.0
        logger.info(f"RAGService constructed ContextPackage in {elapsed:.2f}ms (quality={quality.quality_score:.2f}).")
        return package

    def assemble_prompt_package(
        self,
        context_package: ContextPackage,
        max_tokens: int = 2048,
    ) -> PromptPackage:
        """
        Assemble final prompt string package using PromptAssembler.

        Args:
            context_package: ContextPackage instance.
            max_tokens: Max token budget limit.

        Returns:
            PromptPackage instance.
        """
        return self._prompt_assembler.assemble_prompt(
            cag_context=context_package.cag_context,
            retrieved_results=context_package.retrieved_results,
            quality=context_package.quality,
            max_tokens=max_tokens,
        )
