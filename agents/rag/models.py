"""
Domain Models Module for RAG/CAG Subsystem.

Defines all strongly typed Pydantic V2 domain models used across the RAG/CAG intelligence engine.
All models are fully typed, serialisable, and enforce strict metadata and schema integrity.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class DocumentType(str, Enum):
    """Supported document formats and classifications."""

    MARKDOWN = "markdown"
    TEXT = "text"
    JSON = "json"
    YAML = "yaml"
    HTML = "html"
    PDF = "pdf"
    DOCX = "docx"
    RUNBOOK = "runbook"
    VENDOR_DOC = "vendor_doc"
    HISTORICAL_INCIDENT = "historical_incident"
    UNKNOWN = "unknown"


class ChunkingStrategy(str, Enum):
    """Available document chunking strategies."""

    FIXED_SIZE = "fixed_size"
    PARAGRAPH = "paragraph"
    HEADING_AWARE = "heading_aware"
    SEMANTIC = "semantic"


class RetrievalStrategy(str, Enum):
    """Strategy used for knowledge retrieval."""

    DENSE_ONLY = "dense_only"
    SPARSE_BM25 = "sparse_bm25"
    HYBRID_RRF = "hybrid_rrf"
    FILTERED = "filtered"


class ContextQualityStatus(str, Enum):
    """Status classification of context quality evaluation."""

    HIGH_QUALITY = "HIGH_QUALITY"
    ACCEPTABLE = "ACCEPTABLE"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


# ---------------------------------------------------------------------------
# Primitive Models
# ---------------------------------------------------------------------------


class Document(BaseModel):
    """Represents a loaded enterprise knowledge document."""

    model_config = ConfigDict(frozen=False)

    doc_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique document ID")
    filename: str = Field(..., description="Original filename or document name")
    content: str = Field(..., description="Full text content of document")
    document_type: DocumentType = Field(default=DocumentType.UNKNOWN)
    hash: str = Field(default="", description="SHA-256 content hash")
    source: str = Field(default="", description="Source path, URI, or repository name")
    author: str = Field(default="NOC Engineering", description="Document author/creator")
    version: str = Field(default="1.0.0", description="Semantic version string")
    created_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modified_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: List[str] = Field(default_factory=list, description="Categorical classification tags")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary key-value metadata")


class DocumentChunk(BaseModel):
    """Represents a segmented chunk of a Document."""

    model_config = ConfigDict(frozen=False)

    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_doc_id: str = Field(..., description="ID of parent Document")
    chunk_index: int = Field(default=0, description="Sequential position in parent document")
    content: str = Field(..., description="Text payload of the chunk")
    token_count: int = Field(default=0, description="Estimated token count")
    heading_hierarchy: List[str] = Field(default_factory=list, description="Breadcrumb markdown headings")
    chunking_strategy: ChunkingStrategy = Field(default=ChunkingStrategy.FIXED_SIZE)
    source: str = Field(default="")
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if self.token_count == 0 and self.content:
            self.token_count = max(1, len(self.content.split()))



class EmbeddingVector(BaseModel):
    """Vector representation of text or document chunk."""

    model_config = ConfigDict(frozen=False)

    vector_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    chunk_id: str = Field(..., description="Associated DocumentChunk ID")
    values: List[float] = Field(..., description="Dense embedding vector array")
    dimension: int = Field(..., description="Vector dimensionality")
    provider_name: str = Field(default="unknown", description="Embedding provider model name")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SearchMetadata(BaseModel):
    """Query filters and metadata matching options."""

    model_config = ConfigDict(frozen=False)

    device_id: Optional[str] = Field(default=None)
    incident_type: Optional[str] = Field(default=None)
    topology_role: Optional[str] = Field(default=None)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    tags: List[str] = Field(default_factory=list)
    custom_filters: Dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Individual candidate match returned by retrieval engine."""

    model_config = ConfigDict(frozen=False)

    chunk: DocumentChunk = Field(..., description="Matched DocumentChunk")
    score: float = Field(..., description="Composite relevance/similarity score")
    dense_score: float = Field(default=0.0, description="Dense vector similarity score")
    sparse_score: float = Field(default=0.0, description="Sparse BM25 score")
    rerank_score: float = Field(default=0.0, description="Final reranker composite score")
    retrieval_strategy: RetrievalStrategy = Field(default=RetrievalStrategy.HYBRID_RRF)
    rank: int = Field(default=0, description="Final rank position")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    """Structured evidence citation backing an AI conclusion."""

    model_config = ConfigDict(frozen=False)

    citation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    chunk_id: str = Field(..., description="Referenced chunk ID")
    source: str = Field(..., description="Document source or filename")
    section: str = Field(default="", description="Section or heading title")
    content_snippet: str = Field(..., description="Cited text excerpt")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ContextMetrics(BaseModel):
    """Metrics tracking CAG context package statistics."""

    model_config = ConfigDict(frozen=False)

    total_characters: int = Field(default=0)
    total_tokens_estimated: int = Field(default=0)
    telemetry_present: bool = Field(default=False)
    prediction_present: bool = Field(default=False)
    incident_present: bool = Field(default=False)
    recommendation_present: bool = Field(default=False)
    topology_present: bool = Field(default=False)
    retrieved_chunks_count: int = Field(default=0)


class ContextQuality(BaseModel):
    """Evaluation output from ContextQualityEngine."""

    model_config = ConfigDict(frozen=False)

    quality_score: float = Field(..., ge=0.0, le=1.0, description="Overall quality score (0.0 to 1.0)")
    status: ContextQualityStatus = Field(default=ContextQualityStatus.ACCEPTABLE)
    completeness_score: float = Field(default=1.0, ge=0.0, le=1.0)
    freshness_score: float = Field(default=1.0, ge=0.0, le=1.0)
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)
    diversity_score: float = Field(default=1.0, ge=0.0, le=1.0)
    is_sufficient: bool = Field(default=True, description="True if evidence meets quality threshold")
    warnings: List[str] = Field(default_factory=list, description="Quality warnings or missing context notes")
    missing_fields: List[str] = Field(default_factory=list)


class CAGContext(BaseModel):
    """
    Unified operational state context built by ContextBuilder.
    Combines live telemetry, predictions, incidents, recommendations, topology graph,
    historical context, and timestamps.
    """

    model_config = ConfigDict(frozen=False)

    context_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    operator_query: str = Field(default="", description="User question or query string")
    device_id: str = Field(default="", description="Primary active device ID")
    interface: str = Field(default="", description="Target network interface name")
    telemetry_data: Dict[str, Any] = Field(default_factory=dict)
    prediction_data: Dict[str, Any] = Field(default_factory=dict)
    incident_data: Dict[str, Any] = Field(default_factory=dict)
    recommendation_data: Dict[str, Any] = Field(default_factory=dict)
    topology_data: Dict[str, Any] = Field(default_factory=dict)
    historical_incidents: List[Dict[str, Any]] = Field(default_factory=list)
    device_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: ContextMetrics = Field(default_factory=ContextMetrics)


class ContextPackage(BaseModel):
    """Bundle containing CAGContext, retrieved results, citations, and quality score."""

    model_config = ConfigDict(frozen=False)

    package_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cag_context: CAGContext = Field(..., description="Unified CAG operational state")
    retrieved_results: List[RetrievalResult] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)
    quality: ContextQuality = Field(default_factory=lambda: ContextQuality(quality_score=1.0, is_sufficient=True))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PromptPackage(BaseModel):
    """Final assembled prompt package with token budgeting and citations."""

    model_config = ConfigDict(frozen=False)

    prompt_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    assembled_prompt: str = Field(..., description="Complete prompt text string sent to LLM")
    system_instruction: str = Field(default="")
    user_query: str = Field(default="")
    token_count_estimated: int = Field(default=0)
    was_compressed: bool = Field(default=False)
    citations: List[Citation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RAGResult(BaseModel):
    """Complete output artefact returned by RAGService."""

    model_config = ConfigDict(frozen=False)

    rag_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: str = Field(...)
    device_id: str = Field(default="")
    generated_text: str = Field(..., description="LLM response completion text")
    citations: List[Citation] = Field(default_factory=list)
    context_quality: ContextQuality = Field(
        default_factory=lambda: ContextQuality(quality_score=1.0, is_sufficient=True)
    )
    retrieved_chunks_count: int = Field(default=0)
    execution_time_ms: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)
