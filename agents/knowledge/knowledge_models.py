"""
Domain Models and Schemas for Knowledge Agent Subsystem.

Provides strongly typed Pydantic v2 models for knowledge queries, knowledge results,
cache entries, and operational statistics.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeQuery(BaseModel):
    """Data model representing a knowledge generation request."""

    model_config = ConfigDict(frozen=False)

    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    recommendation_id: str = Field(..., description="Source recommendation ID (e.g. REC-2026-000001)")
    incident_id: str = Field(..., description="Source incident ID (e.g. INC-2026-000001)")
    device_id: str = Field(..., description="Monitored device ID or interface")
    prompt_text: str = Field(..., description="Constructed prompt text string")
    context_documents: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeResult(BaseModel):
    """Primary knowledge result data model representing LLM-generated operational insights."""

    model_config = ConfigDict(frozen=False)

    result_id: str = Field(..., description="Sequential ID e.g. KNOW-2026-000001")
    query_id: str = Field(..., description="Associated query ID")
    recommendation_id: str = Field(..., description="Associated recommendation ID")
    incident_id: str = Field(..., description="Associated incident ID")
    device_id: str = Field(..., description="Associated device ID or interface")
    generated_explanation: str = Field(..., description="Full LLM-generated analysis text")
    root_cause_analysis: str = Field(default="", description="Summarized root cause hypothesis")
    recommended_steps: List[str] = Field(default_factory=list, description="Recommended remediation steps")
    confidence_score: float = Field(default=0.85, ge=0.0, le=1.0, description="Model confidence score")
    cited_sources: List[str] = Field(default_factory=list, description="Retrieved doc citations")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provider_metadata: Dict[str, Any] = Field(default_factory=dict, description="LLM provider metadata")


class KnowledgeCacheEntry(BaseModel):
    """In-memory cache record."""

    model_config = ConfigDict(frozen=False)

    cache_key: str = Field(...)
    result: KnowledgeResult = Field(...)
    cached_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: float = Field(default=3600.0)

    def is_expired(self) -> bool:
        """Check if cache entry has exceeded TTL."""
        elapsed = (datetime.now(timezone.utc) - self.cached_at).total_seconds()
        return elapsed > self.ttl_seconds


class KnowledgeStatistics(BaseModel):
    """Aggregated knowledge subsystem statistics."""

    model_config = ConfigDict(frozen=False)

    total_queries: int = Field(default=0)
    cache_hits: int = Field(default=0)
    cache_misses: int = Field(default=0)
    average_latency_ms: float = Field(default=0.0)
