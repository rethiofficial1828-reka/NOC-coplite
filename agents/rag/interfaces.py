"""
Interfaces Module for RAG/CAG Subsystem.

Defines formal Abstract Base Classes (interfaces) for all RAG and CAG sub-components,
ensuring strict decoupling, testability, and framework independence.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from agents.rag.models import (
    CAGContext,
    Citation,
    ContextPackage,
    ContextQuality,
    Document,
    DocumentChunk,
    EmbeddingVector,
    PromptPackage,
    RetrievalResult,
    SearchMetadata,
)


class IDocumentLoader(ABC):
    """Abstract interface for loading enterprise documents."""

    @abstractmethod
    def load_document(self, file_path: str) -> Document:
        """Load a single document file into a Document model."""
        pass

    @abstractmethod
    def load_directory(
        self, directory_path: str, recursive: bool = True
    ) -> List[Document]:
        """Load all supported documents from a directory."""
        pass


class IDocumentChunker(ABC):
    """Abstract interface for chunking Document instances."""

    @abstractmethod
    def chunk_document(self, document: Document) -> List[DocumentChunk]:
        """Chunk a Document into a list of DocumentChunk instances."""
        pass


class IEmbeddingProvider(ABC):
    """Abstract interface for generating dense text embeddings."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider model name identifier."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of vector embeddings."""
        pass

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generate a dense vector float list for text."""
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate dense vector float lists for a batch of texts."""
        pass


class IVectorStore(ABC):
    """Abstract interface for dense vector persistence and similarity search."""

    @abstractmethod
    def insert(self, chunk: DocumentChunk, vector: List[float]) -> None:
        """Insert a chunk and its dense embedding vector into the store."""
        pass

    @abstractmethod
    def batch_insert(
        self, chunks: List[DocumentChunk], vectors: List[List[float]]
    ) -> None:
        """Insert a batch of chunks and vectors into the store."""
        pass

    @abstractmethod
    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        search_metadata: Optional[SearchMetadata] = None,
    ) -> List[RetrievalResult]:
        """Search for top_k nearest chunks matching query_vector and optional metadata filters."""
        pass

    @abstractmethod
    def delete(self, chunk_id: str) -> bool:
        """Delete a chunk by ID."""
        pass

    @abstractmethod
    def count(self) -> int:
        """Return total number of stored vectors."""
        pass


class IKeywordIndex(ABC):
    """Abstract interface for sparse BM25 keyword search."""

    @abstractmethod
    def index_chunks(self, chunks: List[DocumentChunk]) -> None:
        """Index a batch of DocumentChunk instances."""
        pass

    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 5,
        search_metadata: Optional[SearchMetadata] = None,
    ) -> List[RetrievalResult]:
        """Execute sparse BM25 search over indexed chunks."""
        pass


class IHybridRetriever(ABC):
    """Abstract interface for hybrid (Dense + BM25) candidate retrieval."""

    @abstractmethod
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        search_metadata: Optional[SearchMetadata] = None,
    ) -> List[RetrievalResult]:
        """Perform hybrid candidate retrieval."""
        pass


class IReranker(ABC):
    """Abstract interface for multi-factor candidate reranking."""

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: List[RetrievalResult],
        context: Optional[CAGContext] = None,
        top_k: int = 5,
    ) -> List[RetrievalResult]:
        """Rerank candidate retrieval results."""
        pass


class IContextBuilder(ABC):
    """Abstract interface for Context-Augmented Generation (CAG) state assembly."""

    @abstractmethod
    def build_context(
        self,
        query: str = "",
        device_id: str = "",
        execution_context: Optional[Any] = None,
    ) -> CAGContext:
        """Build a unified CAG operational context package."""
        pass


class IContextQualityEvaluator(ABC):
    """Abstract interface for evaluating context quality and evidence sufficiency."""

    @abstractmethod
    def evaluate_quality(
        self, context: CAGContext, retrieved_chunks: List[RetrievalResult]
    ) -> ContextQuality:
        """Evaluate context quality and return ContextQuality model."""
        pass


class IPromptAssembler(ABC):
    """Abstract interface for token-budgeted enterprise prompt assembly."""

    @abstractmethod
    def assemble_prompt(
        self,
        cag_context: CAGContext,
        retrieved_results: List[RetrievalResult],
        quality: Optional[ContextQuality] = None,
        max_tokens: int = 2048,
    ) -> PromptPackage:
        """Assemble a prompt package ready for LLM consumption."""
        pass
