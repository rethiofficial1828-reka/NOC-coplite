"""
Strongly Typed Pydantic V2 Domain Models for Enterprise AI Reasoning & Evidence Correlation Engine.

Provides models for evidence correlation, hypothesis generation, contradiction detection,
evidence validation, dynamic confidence computation, root cause ranking, and explainable conclusions.
All models support serialization and persistence.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, ConfigDict


class HypothesisCategory(str, Enum):
    """Categorical classification of failure hypotheses."""

    WAN_CONGESTION = "WAN_CONGESTION"
    ROUTING_INSTABILITY = "ROUTING_INSTABILITY"
    HARDWARE_INTERFACE_FLAPPING = "HARDWARE_INTERFACE_FLAPPING"
    ISP_DEGRADATION = "ISP_DEGRADATION"
    QOS_MISCONFIGURATION = "QOS_MISCONFIGURATION"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    UNKNOWN_ANOMALY = "UNKNOWN_ANOMALY"


class ContradictionSeverity(str, Enum):
    """Severity levels of detected evidence contradictions."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReasoningEvidence(BaseModel):
    """Normalized evidence item used internally by the reasoning engine."""

    model_config = ConfigDict(frozen=False)

    evidence_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_agent: str = Field(..., description="Source agent name")
    evidence_type: str = Field(..., description="Classification category")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    device_id: Optional[str] = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    normalized_score: float = Field(default=1.0, ge=0.0, le=1.0)


class EvidenceGroup(BaseModel):
    """Clustered group of related evidence items for a device or anomaly domain."""

    model_config = ConfigDict(frozen=False)

    group_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    group_name: str = Field(..., description="Descriptive group identifier")
    device_id: Optional[str] = Field(default=None)
    primary_type: str = Field(default="general")
    evidence_ids: List[str] = Field(default_factory=list)
    merged_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    summary: str = Field(default="")


class EvidenceCorrelation(BaseModel):
    """Structured correlation result across all collected evidence."""

    model_config = ConfigDict(frozen=False)

    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    groups: List[EvidenceGroup] = Field(default_factory=list)
    total_evidence_count: int = Field(default=0, ge=0)
    correlation_matrix: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    key_findings: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Hypothesis(BaseModel):
    """Competing explanation for observed network failure symptoms."""

    model_config = ConfigDict(frozen=False)

    hypothesis_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(..., description="Short hypothesis title")
    description: str = Field(..., description="Detailed explanation of failure mechanism")
    category: HypothesisCategory = Field(default=HypothesisCategory.UNKNOWN_ANOMALY)
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    missing_evidence_descriptions: List[str] = Field(default_factory=list)
    initial_likelihood: float = Field(default=0.5, ge=0.0, le=1.0)
    coverage_score: float = Field(default=0.5, ge=0.0, le=1.0)


class HypothesisScore(BaseModel):
    """Scoring breakdown for a evaluated hypothesis."""

    model_config = ConfigDict(frozen=False)

    hypothesis_id: str = Field(...)
    raw_score: float = Field(default=0.0)
    normalized_score: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_support_weight: float = Field(default=0.0)
    contradiction_penalty: float = Field(default=0.0)
    confidence_adjustment: float = Field(default=0.0)


class Contradiction(BaseModel):
    """Identified conflict between evidence items."""

    model_config = ConfigDict(frozen=False)

    contradiction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_a: str = Field(..., description="First conflicting source")
    source_b: str = Field(..., description="Second conflicting source")
    description: str = Field(..., description="Explanation of contradiction")
    severity: ContradictionSeverity = Field(default=ContradictionSeverity.MEDIUM)
    conflicting_evidence_ids: List[str] = Field(default_factory=list)
    penalty_factor: float = Field(default=0.15, ge=0.0, le=1.0)


class ValidationResult(BaseModel):
    """Quality and validity assessment for an individual evidence item."""

    model_config = ConfigDict(frozen=False)

    evidence_id: str = Field(...)
    is_valid: bool = Field(default=True)
    freshness_score: float = Field(default=1.0, ge=0.0, le=1.0)
    completeness_score: float = Field(default=1.0, ge=0.0, le=1.0)
    reliability_score: float = Field(default=1.0, ge=0.0, le=1.0)
    issues: List[str] = Field(default_factory=list)


class ConfidenceFactors(BaseModel):
    """Multi-factor parameters driving dynamic confidence calculation."""

    model_config = ConfigDict(frozen=False)

    evidence_quality: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_completeness: float = Field(default=1.0, ge=0.0, le=1.0)
    cross_source_agreement: float = Field(default=1.0, ge=0.0, le=1.0)
    prediction_certainty: float = Field(default=1.0, ge=0.0, le=1.0)
    topology_certainty: float = Field(default=1.0, ge=0.0, le=1.0)
    retrieval_quality: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_score: float = Field(default=1.0, ge=0.0, le=1.0)
    contradiction_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    freshness: float = Field(default=1.0, ge=0.0, le=1.0)


class ConfidenceResult(BaseModel):
    """Composite confidence score output."""

    model_config = ConfigDict(frozen=False)

    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    per_hypothesis_confidence: Dict[str, float] = Field(default_factory=dict)
    evidence_sufficiency_score: float = Field(default=1.0, ge=0.0, le=1.0)
    investigation_completeness_score: float = Field(default=1.0, ge=0.0, le=1.0)
    factors: ConfidenceFactors = Field(default_factory=ConfidenceFactors)


class RootCause(BaseModel):
    """Identified primary or secondary root cause."""

    model_config = ConfigDict(frozen=False)

    cause_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(...)
    probability: float = Field(..., ge=0.0, le=1.0)
    description: str = Field(...)
    affected_components: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)


class RankedRootCause(BaseModel):
    """Ranked hypothesis/root-cause entry."""

    model_config = ConfigDict(frozen=False)

    rank: int = Field(..., ge=1)
    root_cause: RootCause = Field(...)
    final_score: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(...)
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    contradiction_count: int = Field(default=0, ge=0)


class ReasoningExplanation(BaseModel):
    """Explainable structured reasoning summary for operators."""

    model_config = ConfigDict(frozen=False)

    selected_root_cause_title: str = Field(...)
    why_chosen: str = Field(...)
    supporting_evidence_summary: str = Field(...)
    rejected_hypotheses: List[Dict[str, Any]] = Field(default_factory=list)
    contradictions_summary: str = Field(...)
    evidence_quality_summary: str = Field(...)
    missing_evidence_summary: str = Field(...)
    recommended_next_steps: List[str] = Field(default_factory=list)


class InvestigationConclusion(BaseModel):
    """Final conclusion payload produced by ReasoningService."""

    model_config = ConfigDict(frozen=False)

    conclusion_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = Field(...)
    primary_root_cause: Optional[RootCause] = Field(default=None)
    ranked_root_causes: List[RankedRootCause] = Field(default_factory=list)
    ranked_hypotheses: List[Hypothesis] = Field(default_factory=list)
    contradictions: List[Contradiction] = Field(default_factory=list)
    confidence_result: ConfidenceResult = Field(..., description="Confidence scores")
    explanation: Optional[ReasoningExplanation] = Field(default=None, description="Explainable reasoning summary")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReasoningStatistics(BaseModel):
    """Performance statistics for reasoning execution."""

    model_config = ConfigDict(frozen=False)

    evidence_processed: int = Field(default=0, ge=0)
    hypotheses_evaluated: int = Field(default=0, ge=0)
    contradictions_found: int = Field(default=0, ge=0)
    processing_duration_ms: float = Field(default=0.0, ge=0.0)


class ReasoningResult(BaseModel):
    """Overall output payload returned by ReasoningAgent."""

    model_config = ConfigDict(frozen=False)

    reasoning_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = Field(...)
    conclusion: InvestigationConclusion = Field(...)
    correlation: Optional[EvidenceCorrelation] = Field(default=None)
    statistics: ReasoningStatistics = Field(default_factory=ReasoningStatistics)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
