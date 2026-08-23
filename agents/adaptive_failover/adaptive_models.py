"""
Adaptive Models Module for Adaptive Multi-Provider Failover, Failback & Network Stability Intelligence.

Defines Pydantic V2 domain models and enums representing provider health snapshots, hysteresis policies,
oscillation risk assessments, degradation events, transition state machine records, failback candidate
assessments, continuous post-failover verification results, and adaptive failover statistics.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from agents.failover.failover_models import (
    ApprovalStatus,
    ExecutionMode,
    ExecutionStatus,
    FailoverApproval,
    VerificationStatus,
)
from agents.path_decision.path_models import DataOrigin


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ProviderState(str, Enum):
    """Classification state of a network provider or link."""

    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"
    UNKNOWN = "UNKNOWN"


class PathStability(str, Enum):
    """Stability classification of a network path."""

    STABLE = "STABLE"
    UNSTABLE = "UNSTABLE"
    FLAPPING = "FLAPPING"
    OSCILLATING = "OSCILLATING"
    UNKNOWN = "UNKNOWN"


class TransitionReason(str, Enum):
    """Rationale for a provider state transition."""

    HIGH_LATENCY = "HIGH_LATENCY"
    PACKET_LOSS = "PACKET_LOSS"
    HIGH_UTILIZATION = "HIGH_UTILIZATION"
    FAILURE_RISK = "FAILURE_RISK"
    HARD_FAILURE = "HARD_FAILURE"
    PRIMARY_RECOVERED = "PRIMARY_RECOVERED"
    SLA_VIOLATION = "SLA_VIOLATION"
    MANUAL_OPERATOR = "MANUAL_OPERATOR"
    UNKNOWN = "UNKNOWN"


class TransitionStatus(str, Enum):
    """State machine taxonomy for network provider transitions."""

    STABLE = "STABLE"
    DEGRADING = "DEGRADING"
    FAILOVER_CANDIDATE = "FAILOVER_CANDIDATE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    PRECHECK = "PRECHECK"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    STABLE_ON_ALTERNATE = "STABLE_ON_ALTERNATE"
    FAILBACK_CANDIDATE = "FAILBACK_CANDIDATE"
    STABLE_ON_PRIMARY = "STABLE_ON_PRIMARY"


class FailbackStatus(str, Enum):
    """Status classification for safe failback to primary provider."""

    NOT_REQUIRED = "NOT_REQUIRED"
    WAIT_FOR_STABILITY = "WAIT_FOR_STABILITY"
    FAILBACK_RECOMMENDED = "FAILBACK_RECOMMENDED"
    FAILBACK_BLOCKED = "FAILBACK_BLOCKED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StabilityLevel(str, Enum):
    """Quantitative stability classification level."""

    EXCELLENT = "EXCELLENT"
    ACCEPTABLE = "ACCEPTABLE"
    MARGINAL = "MARGINAL"
    UNSTABLE = "UNSTABLE"
    CRITICAL = "CRITICAL"


class OscillationRisk(str, Enum):
    """Oscillation and flapping risk level."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MonitoringState(str, Enum):
    """Status of continuous provider monitor."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Domain Models
# ---------------------------------------------------------------------------


class HysteresisPolicy(BaseModel):
    """Configuration-driven hysteresis and anti-flapping parameters."""

    model_config = ConfigDict(frozen=False)

    minimum_degradation_duration_sec: float = Field(default=30.0, description="Minimum duration degradation must persist before failover")
    minimum_recovery_duration_sec: float = Field(default=60.0, description="Minimum duration primary provider must be healthy before failback")
    minimum_hold_time_sec: float = Field(default=300.0, description="Minimum hold time on a new provider after transition")
    cooldown_after_failover_sec: float = Field(default=120.0, description="Cooldown window after failover before further transitions")
    maximum_transitions_per_hour: int = Field(default=3, description="Maximum allowed transitions per 60-minute window")
    provider_stickiness_weight: float = Field(default=0.15, description="Bonus weight applied to active provider to prevent micro-switching")


class ProviderHealthSnapshot(BaseModel):
    """Snapshot of provider health metrics, trend, and state at a given timestamp."""

    model_config = ConfigDict(frozen=False)

    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    provider_name: str = Field(...)
    wan_interface: str = Field(...)
    health_score: float = Field(default=100.0, ge=0.0, le=100.0)
    health_trend: str = Field(default="STABLE", description="IMPROVING, STABLE, DEGRADED, RAPIDLY_DEGRADED")
    state: ProviderState = Field(default=ProviderState.HEALTHY)
    latency_ms: float = Field(default=15.0)
    packet_loss_percent: float = Field(default=0.0)
    jitter_ms: float = Field(default=2.0)
    utilization_percent: float = Field(default=25.0)
    interface_errors: float = Field(default=0.0)
    interface_flaps: int = Field(default=0)
    failure_risk: float = Field(default=0.01)
    sla_status: str = Field(default="COMPLIANT")
    active_incidents: int = Field(default=0)
    data_origin: DataOrigin = Field(default=DataOrigin.OBSERVED)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PathHealthSnapshot(BaseModel):
    """Snapshot of an entire candidate path."""

    model_config = ConfigDict(frozen=False)

    path_id: str = Field(...)
    source_device: str = Field(...)
    target_device: str = Field(...)
    provider_snapshot: ProviderHealthSnapshot = Field(...)
    stability: PathStability = Field(default=PathStability.STABLE)
    score: float = Field(default=100.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProviderComparison(BaseModel):
    """Comparative analysis of active vs alternative providers."""

    model_config = ConfigDict(frozen=False)

    active_provider: ProviderHealthSnapshot = Field(...)
    alternative_providers: List[ProviderHealthSnapshot] = Field(default_factory=list)
    recommended_provider: Optional[str] = Field(default=None)
    score_delta: float = Field(default=0.0)
    trend_justification: str = Field(default="")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DegradationEvent(BaseModel):
    """Correlated multi-signal degradation event."""

    model_config = ConfigDict(frozen=False)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    provider_name: str = Field(...)
    severity: ProviderState = Field(default=ProviderState.DEGRADED)
    primary_metric: str = Field(...)
    observed_value: float = Field(...)
    threshold_value: float = Field(...)
    duration_sec: float = Field(default=0.0)
    correlated_signals: List[str] = Field(default_factory=list)
    is_hard_failure: bool = Field(default=False)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OscillationAssessment(BaseModel):
    """Assessment of provider flapping and oscillation risk."""

    model_config = ConfigDict(frozen=False)

    provider_name: str = Field(...)
    risk_level: OscillationRisk = Field(default=OscillationRisk.LOW)
    transitions_last_hour: int = Field(default=0)
    time_since_last_transition_sec: float = Field(default=9999.0)
    is_flapping: bool = Field(default=False)
    recommendation: str = Field(default="ALLOW_TRANSITION")


class FailoverTrigger(BaseModel):
    """Trigger decision evaluated by FailoverTriggerEngine."""

    model_config = ConfigDict(frozen=False)

    trigger_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action: str = Field(default="NO_ACTION", description="NO_ACTION, CONTINUE_MONITORING, REQUEST_FAILOVER, FAILOVER_BLOCKED, etc.")
    reason: Any = Field(default=TransitionReason.UNKNOWN)
    active_provider: str = Field(...)
    target_provider: Optional[str] = Field(default=None)
    degradation_event: Optional[DegradationEvent] = Field(default=None)
    oscillation_assessment: Optional[OscillationAssessment] = Field(default=None)
    requires_approval: bool = Field(default=True)
    confidence: float = Field(default=1.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StabilityWindow(BaseModel):
    """Window tracking sustained provider stability before failback."""

    model_config = ConfigDict(frozen=False)

    provider_name: str = Field(...)
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    required_duration_sec: float = Field(default=60.0)
    elapsed_duration_sec: float = Field(default=0.0)
    is_satisfied: bool = Field(default=False)
    average_health_score: float = Field(default=100.0)


class FailbackCandidate(BaseModel):
    """Evaluation candidate for safe failback to primary provider."""

    model_config = ConfigDict(frozen=False)

    primary_provider: str = Field(...)
    current_active_provider: str = Field(...)
    primary_snapshot: ProviderHealthSnapshot = Field(...)
    current_snapshot: ProviderHealthSnapshot = Field(...)
    stability_window: StabilityWindow = Field(...)
    status: FailbackStatus = Field(default=FailbackStatus.WAIT_FOR_STABILITY)
    justification: str = Field(default="")


# Model aliases for backward compatibility & domain terminology
FailbackAssessment = FailbackCandidate
FailoverDecision = FailoverTrigger


class TransitionRecord(BaseModel):
    """Historic record of a network provider transition."""

    model_config = ConfigDict(frozen=False)

    transition_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = Field(...)
    from_provider: str = Field(...)
    to_provider: str = Field(...)
    reason: TransitionReason = Field(...)
    status: TransitionStatus = Field(default=TransitionStatus.STABLE)
    execution_status: ExecutionStatus = Field(default=ExecutionStatus.COMPLETED)
    verification_status: VerificationStatus = Field(default=VerificationStatus.PASSED)
    approval_id: Optional[str] = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContinuousVerificationResult(BaseModel):
    """Post-transition continuous monitoring result."""

    model_config = ConfigDict(frozen=False)

    verification_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    active_provider: str = Field(...)
    before_health: float = Field(...)
    current_health: float = Field(...)
    expected_health: float = Field(...)
    is_improvement: bool = Field(default=True)
    regression_detected: bool = Field(default=False)
    recommended_action: str = Field(default="MAINTAIN_CURRENT")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AdaptiveFailoverResult(BaseModel):
    """Complete domain output for Sprint 19 Adaptive Subsystem."""

    model_config = ConfigDict(frozen=False)

    result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = Field(...)
    active_provider: str = Field(...)
    recommended_provider: str = Field(...)
    transition_status: TransitionStatus = Field(default=TransitionStatus.STABLE)
    failback_status: FailbackStatus = Field(default=FailbackStatus.NOT_REQUIRED)
    provider_comparison: Optional[ProviderComparison] = Field(default=None)
    trigger: Optional[FailoverTrigger] = Field(default=None)
    continuous_verification: Optional[ContinuousVerificationResult] = Field(default=None)
    failback_candidate: Optional[FailbackCandidate] = Field(default=None)
    hysteresis_policy: HysteresisPolicy = Field(default_factory=HysteresisPolicy)
    audit_reference: str = Field(default="")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AdaptiveFailoverStatistics(BaseModel):
    """Subsystem performance statistics."""

    model_config = ConfigDict(frozen=False)

    total_evaluations: int = Field(default=0)
    total_failovers: int = Field(default=0)
    total_failbacks: int = Field(default=0)
    oscillations_blocked: int = Field(default=0)
    active_provider: str = Field(default="ISP-A")
    current_state: TransitionStatus = Field(default=TransitionStatus.STABLE)
