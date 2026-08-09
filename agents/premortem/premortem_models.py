"""
Strongly Typed Pydantic V2 Domain Models for Enterprise Incident Fingerprinting & Pre-Mortem Intelligence Engine.

Provides domain schemas for incident signatures, historical matching, pattern clustering,
future-state prediction, time-to-impact windows, early warnings, and confidence scoring.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, ConfigDict


class ObservationType(str, Enum):
    """Categorical boundary strictly separating observations from predictions and inferences."""

    OBSERVED = "OBSERVED"
    PREDICTED = "PREDICTED"
    INFERRED = "INFERRED"
    HISTORICAL = "HISTORICAL"
    UNKNOWN = "UNKNOWN"


class PreMortemSeverity(str, Enum):
    """Severity classification for future-state scenarios and warnings."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ScenarioType(str, Enum):
    """Types of future-state scenario simulations."""

    BASELINE_PERSISTENCE = "BASELINE_PERSISTENCE"
    TRAFFIC_SURGE = "TRAFFIC_SURGE"
    PATH_DEGRADATION = "PATH_DEGRADATION"
    ALTERNATIVE_PATH_AVAILABLE = "ALTERNATIVE_PATH_AVAILABLE"
    REMEDIATION_APPLIED = "REMEDIATION_APPLIED"
    NO_REMEDIATION_APPLIED = "NO_REMEDIATION_APPLIED"


class EarlyWarningUrgency(str, Enum):
    """Urgency level for early warning indicators."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FingerprintFeature(BaseModel):
    """Individual feature component of a normalized incident fingerprint."""

    model_config = ConfigDict(frozen=False)

    feature_name: str = Field(...)
    feature_value: Any = Field(...)
    category: str = Field(default="telemetry")
    weight: float = Field(default=1.0, ge=0.0, le=5.0)


class IncidentFingerprint(BaseModel):
    """Normalized incident signature model."""

    model_config = ConfigDict(frozen=False)

    fingerprint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    incident_type: str = Field(default="WAN_CONGESTION")
    device_class: str = Field(default="ROUTER")
    interface_pattern: str = Field(default="HIGH_UTILIZATION_WITH_PACKET_LOSS")
    temporal_pattern: str = Field(default="GRADUAL_DEGRADATION")
    prediction_pattern: str = Field(default="INCREASING_FAILURE_RISK")
    topology_pattern: str = Field(default="MULTI_SERVICE_DEPENDENCY")
    features: List[FingerprintFeature] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HistoricalIncidentMatch(BaseModel):
    """Match result against historical incident dataset/vector store."""

    model_config = ConfigDict(frozen=False)

    incident_id: str = Field(...)
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    matching_features: List[str] = Field(default_factory=list)
    differing_features: List[str] = Field(default_factory=list)
    historical_root_cause: str = Field(...)
    historical_resolution: str = Field(...)
    historical_outcome: str = Field(...)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)


class IncidentPattern(BaseModel):
    """Recurring incident failure cluster pattern."""

    model_config = ConfigDict(frozen=False)

    pattern_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pattern_name: str = Field(...)
    category: str = Field(...)
    description: str = Field(...)
    frequency_count: int = Field(default=1, ge=0)
    common_indicators: List[str] = Field(default_factory=list)
    recommended_mitigations: List[str] = Field(default_factory=list)


class ScenarioEvidence(BaseModel):
    """Evidence item tagged with explicit ObservationType classification."""

    model_config = ConfigDict(frozen=False)

    evidence_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str = Field(...)
    observation_type: ObservationType = Field(default=ObservationType.OBSERVED)
    description: str = Field(...)
    confidence: float = Field(default=0.90, ge=0.0, le=1.0)


class FutureScenario(BaseModel):
    """Candidate future-state scenario prediction."""

    model_config = ConfigDict(frozen=False)

    scenario_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scenario_type: ScenarioType = Field(default=ScenarioType.BASELINE_PERSISTENCE)
    description: str = Field(...)
    trigger_conditions: List[str] = Field(default_factory=list)
    expected_signals: List[str] = Field(default_factory=list)
    affected_devices: List[str] = Field(default_factory=list)
    affected_services: List[str] = Field(default_factory=list)
    affected_paths: List[str] = Field(default_factory=list)
    estimated_probability: float = Field(..., ge=0.0, le=1.0)
    severity: PreMortemSeverity = Field(default=PreMortemSeverity.MEDIUM)
    estimated_time_to_impact_minutes: float = Field(default=10.0, ge=0.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: List[ScenarioEvidence] = Field(default_factory=list)
    mitigation_options: List[str] = Field(default_factory=list)


class TimeToImpact(BaseModel):
    """Impact window estimation model returning realistic ranges."""

    model_config = ConfigDict(frozen=False)

    min_time_minutes: float = Field(..., ge=0.0)
    max_time_minutes: float = Field(..., ge=0.0)
    expected_time_minutes: float = Field(..., ge=0.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    threshold_type: str = Field(default="SLA_BREACH")
    impact_description: str = Field(...)


class EarlyWarning(BaseModel):
    """Early warning notification for approaching failure patterns."""

    model_config = ConfigDict(frozen=False)

    warning_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    urgency: EarlyWarningUrgency = Field(default=EarlyWarningUrgency.HIGH)
    title: str = Field(...)
    message: str = Field(...)
    matched_pattern: str = Field(...)
    observed_signals: List[str] = Field(default_factory=list)
    predicted_next_state: str = Field(...)
    confidence: float = Field(..., ge=0.0, le=1.0)
    recommended_investigation: str = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PreMortemConfidence(BaseModel):
    """Multi-factor pre-mortem confidence assessment."""

    model_config = ConfigDict(frozen=False)

    score: float = Field(..., ge=0.0, le=1.0)
    confidence_level: str = Field(default="HIGH")
    supporting_factors: List[str] = Field(default_factory=list)
    uncertainty_factors: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)


class PreMortemResult(BaseModel):
    """Complete output payload of PreMortemEngine."""

    model_config = ConfigDict(frozen=False)

    premortem_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    investigation_id: str = Field(...)
    request_id: str = Field(...)
    fingerprint: IncidentFingerprint = Field(...)
    historical_matches: List[HistoricalIncidentMatch] = Field(default_factory=list)
    pattern_clusters: List[IncidentPattern] = Field(default_factory=list)
    scenarios: List[FutureScenario] = Field(default_factory=list)
    time_to_impact: TimeToImpact = Field(...)
    early_warnings: List[EarlyWarning] = Field(default_factory=list)
    confidence: PreMortemConfidence = Field(...)
    summary: str = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PreMortemStatistics(BaseModel):
    """Runtime execution statistics for PreMortemEngine."""

    model_config = ConfigDict(frozen=False)

    total_evaluations: int = Field(default=0, ge=0)
    scenarios_generated: int = Field(default=0, ge=0)
    early_warnings_detected: int = Field(default=0, ge=0)
    avg_similarity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_processing_time_ms: float = Field(default=0.0, ge=0.0)
