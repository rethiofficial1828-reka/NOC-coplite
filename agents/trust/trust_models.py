"""
Strongly Typed Pydantic V2 Domain Models for Enterprise Trust, Verification & Safe Autonomy Engine.

Provides models for evidence re-validation, adversarial verification, counterfactual analysis,
blast radius calculation, autonomy policy enforcement, trust scoring, and decision explainability.
All models support serialization and persistence.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, ConfigDict


class VerificationStatus(str, Enum):
    """Status of adversarial and evidence verification checks."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONTRADICTED = "CONTRADICTED"


class AutonomyLevel(str, Enum):
    """Categorical levels of system execution autonomy."""

    FULL_AUTONOMY = "FULL_AUTONOMY"
    SUPERVISED_AUTONOMY = "SUPERVISED_AUTONOMY"
    HUMAN_ONLY = "HUMAN_ONLY"
    BLOCKED = "BLOCKED"


class AutonomyDecision(str, Enum):
    """Final actionable safety decision outcome."""

    AUTO_ELIGIBLE = "AUTO_ELIGIBLE"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    ADDITIONAL_EVIDENCE_REQUIRED = "ADDITIONAL_EVIDENCE_REQUIRED"
    BLOCKED = "BLOCKED"


# Compatibility alias for safe autonomy policy decisions
AutonomyPolicyResult = AutonomyDecision


class BlastRadiusLevel(str, Enum):
    """Impact severity rating for current incidents or potential operational actions."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DecisionLifecycleState(str, Enum):
    """Lifecycle state transition sequence for safe autonomy decisions."""

    PROPOSED = "PROPOSED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONTRADICTED = "CONTRADICTED"
    TRUST_ASSESSED = "TRUST_ASSESSED"
    AUTONOMY_EVALUATED = "AUTONOMY_EVALUATED"
    DECISION_READY = "DECISION_READY"


class VerificationEvidence(BaseModel):
    """Re-validated evidence record."""

    model_config = ConfigDict(frozen=False)

    evidence_id: str = Field(...)
    source_agent: str = Field(...)
    evidence_type: str = Field(...)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_valid: bool = Field(default=True)
    freshness_score: float = Field(default=1.0, ge=0.0, le=1.0)
    reliability_score: float = Field(default=1.0, ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)


class VerificationFinding(BaseModel):
    """Detailed finding produced during verification or adversarial analysis."""

    model_config = ConfigDict(frozen=False)

    finding_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(...)
    status: VerificationStatus = Field(default=VerificationStatus.PASSED)
    description: str = Field(...)
    affected_evidence_ids: List[str] = Field(default_factory=list)
    severity: str = Field(default="MEDIUM")


class AdversarialChallenge(BaseModel):
    """Structured question challenging a proposed root cause hypothesis."""

    model_config = ConfigDict(frozen=False)

    challenge_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str = Field(..., description="Challenging question attempting to disprove hypothesis")
    rationale: str = Field(...)
    target_hypothesis_id: str = Field(...)
    challenged_by: str = Field(default="AdversarialVerifier")
    result_status: VerificationStatus = Field(default=VerificationStatus.PASSED)


class AdversarialResult(BaseModel):
    """Outcome of adversarial verification probing."""

    model_config = ConfigDict(frozen=False)

    is_disproved: bool = Field(default=False)
    challenge_count: int = Field(default=0, ge=0)
    passed_challenges: int = Field(default=0, ge=0)
    failed_challenges: int = Field(default=0, ge=0)
    challenges: List[AdversarialChallenge] = Field(default_factory=list)
    findings: List[VerificationFinding] = Field(default_factory=list)
    penalty_factor: float = Field(default=0.0, ge=0.0, le=1.0)


class CounterfactualHypothesis(BaseModel):
    """Counterfactual scenario testing: 'If hypothesis were false, what would we see?'"""

    model_config = ConfigDict(frozen=False)

    hypothesis_id: str = Field(...)
    counterfactual_statement: str = Field(...)
    expected_evidence: List[str] = Field(default_factory=list)
    observed_evidence: List[str] = Field(default_factory=list)
    is_supported: bool = Field(default=True)


class CounterfactualResult(BaseModel):
    """Output of counterfactual analysis engine."""

    model_config = ConfigDict(frozen=False)

    counterfactual_hypotheses: List[CounterfactualHypothesis] = Field(default_factory=list)
    total_supported: int = Field(default=0, ge=0)
    total_contradicted: int = Field(default=0, ge=0)
    confidence_adjustment: float = Field(default=0.0)
    conclusion: str = Field(...)


class EvidenceRevalidation(BaseModel):
    """Summary of evidence re-validation phase."""

    model_config = ConfigDict(frozen=False)

    revalidated_items: List[VerificationEvidence] = Field(default_factory=list)
    valid_count: int = Field(default=0, ge=0)
    stale_count: int = Field(default=0, ge=0)
    invalid_count: int = Field(default=0, ge=0)
    overall_quality_score: float = Field(default=1.0, ge=0.0, le=1.0)


class AffectedDevice(BaseModel):
    """Device within blast radius domain."""

    model_config = ConfigDict(frozen=False)

    device_id: str = Field(...)
    name: str = Field(...)
    device_type: str = Field(default="router")
    role: str = Field(default="access")
    is_critical: bool = Field(default=False)


class AffectedInterface(BaseModel):
    """Network interface within blast radius domain."""

    model_config = ConfigDict(frozen=False)

    interface_id: str = Field(...)
    device_id: str = Field(...)
    name: str = Field(...)
    bandwidth_capacity: float = Field(default=1000.0)


class AffectedService(BaseModel):
    """Higher-layer business service within blast radius domain."""

    model_config = ConfigDict(frozen=False)

    service_id: str = Field(...)
    name: str = Field(...)
    criticality: str = Field(default="MEDIUM")
    user_count: int = Field(default=0, ge=0)


class AffectedPath(BaseModel):
    """Network path or topology link affected."""

    model_config = ConfigDict(frozen=False)

    path_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_device: str = Field(...)
    target_device: str = Field(...)
    hop_count: int = Field(default=1, ge=1)
    is_redundant: bool = Field(default=True)


class BlastRadiusComponent(BaseModel):
    """Individual impact component descriptor."""

    model_config = ConfigDict(frozen=False)

    component_type: str = Field(...)
    component_id: str = Field(...)
    impact_level: BlastRadiusLevel = Field(default=BlastRadiusLevel.LOW)


class BlastRadius(BaseModel):
    """Blast radius assessment explicitly distinguishing current incident vs. potential action impact."""

    model_config = ConfigDict(frozen=False)

    current_incident_level: BlastRadiusLevel = Field(default=BlastRadiusLevel.LOW)
    potential_action_level: BlastRadiusLevel = Field(default=BlastRadiusLevel.MEDIUM)
    current_affected_devices: List[AffectedDevice] = Field(default_factory=list)
    potential_affected_devices: List[AffectedDevice] = Field(default_factory=list)
    current_affected_services: List[AffectedService] = Field(default_factory=list)
    potential_affected_services: List[AffectedService] = Field(default_factory=list)
    score: float = Field(default=0.3, ge=0.0, le=1.0, description="Normalized blast radius score")
    is_action_larger_than_incident: bool = Field(default=False)
    detailed_components: List[BlastRadiusComponent] = Field(default_factory=list)


class AutonomyPolicy(BaseModel):
    """Configurable autonomy policy thresholds."""

    model_config = ConfigDict(frozen=False)

    policy_id: str = Field(default="default-policy")
    min_trust_score: float = Field(default=0.85, ge=0.0, le=1.0)
    max_blast_radius: BlastRadiusLevel = Field(default=BlastRadiusLevel.MEDIUM)
    require_reversibility: bool = Field(default=True)
    require_rollback_plan: bool = Field(default=True)
    allow_auto_execution: bool = Field(default=True)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConfidenceHandoff(BaseModel):
    """Assessment evaluating handoff to human operator or automated workflow."""

    model_config = ConfigDict(frozen=False)

    recommendation_id: Optional[str] = Field(default=None)
    handoff_decision: AutonomyDecision = Field(default=AutonomyDecision.HUMAN_APPROVAL_REQUIRED)
    confidence_score: float = Field(default=0.8, ge=0.0, le=1.0)
    evidence_quality: float = Field(default=0.8, ge=0.0, le=1.0)
    contradiction_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning_summary: str = Field(...)


class DecisionFactor(BaseModel):
    """Individual parameter factor contributing to overall TrustScore and decision."""

    model_config = ConfigDict(frozen=False)

    factor_name: str = Field(...)
    score: float = Field(..., ge=0.0, le=1.0)
    weight: float = Field(..., ge=0.0, le=1.0)
    contribution: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(...)


class DecisionExplanation(BaseModel):
    """Structured, auditable explanation of final safety decision."""

    model_config = ConfigDict(frozen=False)

    why_selected: str = Field(...)
    why_not_alternative: str = Field(...)
    supporting_evidence: List[str] = Field(default_factory=list)
    contradicting_evidence: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)
    verification_result: str = Field(...)
    counterfactual_result: str = Field(...)
    blast_radius_reason: str = Field(...)
    autonomy_reason: str = Field(...)
    risk_factors: List[str] = Field(default_factory=list)
    recommended_next_step: str = Field(...)


class TrustScore(BaseModel):
    """Multi-dimensional composite trust scoring."""

    model_config = ConfigDict(frozen=False)

    reasoning_confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_confidence: float = Field(..., ge=0.0, le=1.0)
    verification_confidence: float = Field(..., ge=0.0, le=1.0)
    operational_safety_score: float = Field(..., ge=0.0, le=1.0)
    overall_trust_score: float = Field(..., ge=0.0, le=1.0)
    breakdown: List[DecisionFactor] = Field(default_factory=list)


class TrustAssessment(BaseModel):
    """Complete trust evaluation container."""

    model_config = ConfigDict(frozen=False)

    assessment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trust_score: TrustScore = Field(...)
    verification_status: VerificationStatus = Field(...)
    blast_radius: BlastRadius = Field(...)
    lifecycle_state: DecisionLifecycleState = Field(default=DecisionLifecycleState.TRUST_ASSESSED)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrustDecision(BaseModel):
    """Final non-executing safety decision payload returned by TrustAgent."""

    model_config = ConfigDict(frozen=False)

    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    investigation_id: str = Field(...)
    request_id: str = Field(...)
    decision: AutonomyDecision = Field(..., description="Action safety decision")
    lifecycle_state: DecisionLifecycleState = Field(default=DecisionLifecycleState.DECISION_READY)
    trust_assessment: TrustAssessment = Field(...)
    handoff: ConfidenceHandoff = Field(...)
    explanation: DecisionExplanation = Field(...)
    policy_applied: AutonomyPolicy = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrustStatistics(BaseModel):
    """Runtime statistics for trust evaluations."""

    model_config = ConfigDict(frozen=False)

    total_assessments: int = Field(default=0, ge=0)
    auto_eligible_count: int = Field(default=0, ge=0)
    human_approval_count: int = Field(default=0, ge=0)
    blocked_count: int = Field(default=0, ge=0)
    avg_trust_score: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_processing_time_ms: float = Field(default=0.0, ge=0.0)


# Bind class-level attribute descriptors for model fields to support MagicMock spec reflection
for _model in (TrustDecision, TrustAssessment):
    for _field_name in _model.model_fields:
        if not hasattr(_model, _field_name):
            setattr(_model, _field_name, None)
