"""
Enterprise CAG + RAG Intelligence Engine Package — Sprint 11.

Provides the production-grade Context-Augmented Generation (CAG) and
Retrieval-Augmented Generation (RAG) subsystem for NOC Copilot.

Exported symbols:
    RAGAgent                    — BaseAgent subclass for RAG orchestration
    RAGService                  — Central business logic pipeline service
    ContextBuilder              — Aggregates live operational context across agents (CAG)
    DocumentLoader              — Multi-format enterprise document parser
    IntelligentChunker          — Semantic heading/paragraph chunker
    EmbeddingProvider           — Abstract embedding interface & implementations
    EmbeddingProviderFactory     — Dynamic provider factory
    SQLiteVectorStore           — Persistent vector store
    VectorStoreFactory          — Dynamic vector store factory
    KeywordIndex                — Full BM25 sparse keyword search index
    HybridRetriever             — Dense + BM25 + metadata filtering retriever
    Reranker                    — Multi-factor semantic reranking engine
    PromptAssembler             — Enterprise prompt construction & token budget manager
    Document                    — Pydantic V2 document domain model
    DocumentChunk               — Pydantic V2 chunk domain model
    RAGResult                   — Pydantic V2 output result model
    CAGContext                  — Pydantic V2 CAG unified context model
    register_rag_agent          — Helper to register RAGAgent with AgentRegistry
"""

from agents.rag.models import (
    CAGContext,
    Citation,
    ContextPackage,
    ContextQuality,
    Document,
    DocumentChunk,
    EmbeddingVector,
    PromptPackage,
    RAGResult,
    RetrievalResult,
    SearchMetadata,
)
from agents.rag.interfaces import (
    IContextBuilder,
    IDocumentChunker,
    IDocumentLoader,
    IEmbeddingProvider,
    IHybridRetriever,
    IKeywordIndex,
    IPromptAssembler,
    IReranker,
    IVectorStore,
)
from agents.rag.document_loader import DocumentLoader
from agents.rag.document_chunker import IntelligentChunker
from agents.rag.embedding_provider import (
    BGEEmbeddingProvider,
    NomicEmbeddingProvider,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    SentenceTransformersEmbeddingProvider,
    TFIDFEmbeddingProvider,
)
from agents.rag.embedding_factory import EmbeddingProviderFactory
from agents.rag.vector_store import SQLiteVectorStore
from agents.rag.vector_store_factory import VectorStoreFactory
from agents.rag.keyword_index import KeywordIndex
from agents.rag.retrieval_cache import RetrievalCache
from agents.rag.hybrid_retriever import HybridRetriever
from agents.rag.reranker import Reranker
from agents.rag.context_builder import ContextBuilder
from agents.rag.context_quality import ContextQualityEvaluator
from agents.rag.prompt_assembler import PromptAssembler
from agents.rag.citations import CitationGenerator
from agents.rag.index_manager import IndexManager
from agents.rag.rag_service import RAGService
from agents.rag.rag_agent import RAGAgent, register_rag_agent

# Alias for backward compatibility
DocumentModel = Document

__all__ = [
    "Document",
    "DocumentModel",
    "DocumentChunk",
    "EmbeddingVector",
    "RetrievalResult",
    "Citation",
    "CAGContext",
    "ContextQuality",
    "ContextPackage",
    "PromptPackage",
    "RAGResult",
    "SearchMetadata",
    "IDocumentLoader",
    "IDocumentChunker",
    "IEmbeddingProvider",
    "IVectorStore",
    "IKeywordIndex",
    "IHybridRetriever",
    "IReranker",
    "IContextBuilder",
    "IPromptAssembler",
    "DocumentLoader",
    "IntelligentChunker",
    "TFIDFEmbeddingProvider",
    "SentenceTransformersEmbeddingProvider",
    "OllamaEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "BGEEmbeddingProvider",
    "NomicEmbeddingProvider",
    "EmbeddingProviderFactory",
    "SQLiteVectorStore",
    "VectorStoreFactory",
    "KeywordIndex",
    "RetrievalCache",
    "HybridRetriever",
    "Reranker",
    "ContextBuilder",
    "ContextQualityEvaluator",
    "PromptAssembler",
    "CitationGenerator",
    "IndexManager",
    "RAGService",
    "RAGAgent",
    "register_rag_agent",
]
