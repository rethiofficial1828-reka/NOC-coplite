"""
Path Models Module for Enterprise Intelligent Network Path & Provider Decision Engine.

Defines Pydantic V2 domain models representing candidate network paths, provider health,
path evaluation dimensions, network economics, path scoring, scenario simulations,
failover recommendations, and overall decision results.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SimulationScenario(str, Enum):
    """Scenarios for network path simulation."""

    CURRENT_PATH = "CURRENT_PATH"
    ALTERNATIVE_PATH = "ALTERNATIVE_PATH"
    TRAFFIC_SURGE = "TRAFFIC_SURGE"
    PROVIDER_DEGRADATION = "PROVIDER_DEGRADATION"
    FAILOVER_SCENARIO = "FAILOVER_SCENARIO"
    NO_ACTION = "NO_ACTION"


class DataOrigin(str, Enum):
    """Origin taxonomy for metric and simulation values."""

    OBSERVED = "OBSERVED"
    PREDICTED = "PREDICTED"
    INFERRED = "INFERRED"
    HISTORICAL = "HISTORICAL"
    SIMULATED = "SIMULATED"
    UNKNOWN = "UNKNOWN"


class DecisionStatus(str, Enum):
    """Failover and path decision status classification."""

    KEEP_CURRENT_PATH = "KEEP_CURRENT_PATH"
    MONITOR = "MONITOR"
    INVESTIGATE = "INVESTIGATE"
    RECOMMEND_ALTERNATIVE = "RECOMMEND_ALTERNATIVE"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    BLOCKED = "BLOCKED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class SLAStatus(str, Enum):
    """SLA compliance classification."""

    COMPLIANT = "COMPLIANT"
    VIOLATED = "VIOLATED"
    UNKNOWN = "UNKNOWN"


class EconomicEvaluationStatus(str, Enum):
    """Evaluation status for provider financial economics."""

    EVALUATED = "EVALUATED"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Core Domain Models
# ---------------------------------------------------------------------------


class PathCandidate(BaseModel):
    """Candidate network path discovered from topology and inventory data."""

    model_config = ConfigDict(frozen=False)

    path_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    provider_name: str = Field(..., description="Provider or WAN link name (e.g. ISP-A, ISP-B)")
    wan_interface: str = Field(..., description="Local interface key or WAN port identifier")
    source_device: str = Field(..., description="Source device ID or name")
    destination: str = Field(default="Enterprise Gateway", description="Target destination or service")
    is_primary: bool = Field(default=False, description="Whether this is the primary active path")
    hops: List[str] = Field(default_factory=list, description="Ordered node IDs traversed")
    interfaces: List[str] = Field(default_factory=list, description="Interfaces along the path")
    dependencies: List[str] = Field(default_factory=list, description="Critical topology dependencies")
    is_independent: bool = Field(default=True, description="Whether path is physically/logically redundant")
    single_points_of_failure: List[str] = Field(default_factory=list, description="SPOF node/link IDs")
    bandwidth_mbps: float = Field(default=1000.0, description="Path nominal capacity in Mbps")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom vendor metadata")


# Alias for backward compatibility with legacy tests and imports
CandidatePath = PathCandidate


class ProviderHealthScore(BaseModel):
    """Normalized provider operational health assessment."""

    model_config = ConfigDict(frozen=False)

    provider_name: str = Field(...)
    health_score: float = Field(..., ge=0.0, le=100.0, description="Normalized health score 0-100")
    metrics_available: Dict[str, bool] = Field(default_factory=dict, description="Availability map per metric")
    metric_values: Dict[str, float] = Field(default_factory=dict, description="Raw telemetry metric values")
    xgboost_risk: float = Field(default=0.0, ge=0.0, le=1.0, description="Predictive failure risk from XGBoost")
    active_incidents: int = Field(default=0, description="Count of open incidents on this provider")
    evidence_freshness_sec: float = Field(default=0.0, description="Age of telemetry data in seconds")
    collector_health_status: str = Field(default="HEALTHY", description="Collector health state")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in health calculation")
    rationale: List[str] = Field(default_factory=list, description="Human-readable score rationale")


class PathEvaluation(BaseModel):
    """Multi-dimensional evaluation of a candidate path across 14 criteria."""

    model_config = ConfigDict(frozen=False, populate_by_name=True)

    # candidate_id is a legacy alias for path_id; accepted for backward compatibility
    candidate_id: Optional[str] = Field(default=None, exclude=True)
    path_id: str = Field(default="")
    provider_name: str = Field(default="")
    health: float = Field(..., ge=0.0, le=100.0)
    reliability: float = Field(default=0.0, ge=0.0, le=100.0)
    failure_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_ms: float = Field(default=0.0)
    packet_loss_percent: float = Field(default=0.0)
    jitter_ms: float = Field(default=0.0)
    capacity_mbps: float = Field(default=1000.0)
    utilization_percent: float = Field(default=0.0)
    sla_status: SLAStatus = Field(default=SLAStatus.COMPLIANT)
    topology_independence: float = Field(default=100.0, ge=0.0, le=100.0)
    blast_radius_score: float = Field(default=0.0, ge=0.0, le=1.0)
    historical_reliability: float = Field(default=100.0, ge=0.0, le=100.0)
    evidence_freshness_sec: float = Field(default=0.0)
    collector_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evaluation_details: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _map_candidate_id(cls, values: Any) -> Any:
        """Map legacy candidate_id to path_id for backward compatibility."""
        if isinstance(values, dict):
            if "candidate_id" in values and not values.get("path_id"):
                values["path_id"] = values["candidate_id"]
        return values


class NetworkEconomics(BaseModel):
    """Provider financial economics and failover cost evaluation."""

    model_config = ConfigDict(frozen=False)

    provider_name: str = Field(...)
    economic_status: EconomicEvaluationStatus = Field(default=EconomicEvaluationStatus.UNKNOWN)
    bandwidth_cost_per_gb: Optional[float] = Field(default=None)
    provider_monthly_cost: Optional[float] = Field(default=None)
    committed_bandwidth_mbps: Optional[float] = Field(default=None)
    overage_cost_per_gb: Optional[float] = Field(default=None)
    sla_penalty_rate: Optional[float] = Field(default=None)
    estimated_failover_cost: Optional[float] = Field(default=None)
    capacity_available_mbps: Optional[float] = Field(default=None)
    business_priority: int = Field(default=5, ge=1, le=10)
    explanation: str = Field(
        default="Network economics could not be evaluated because provider pricing data is unavailable."
    )


class PathScore(BaseModel):
    """Deterministic weighted ranking score for a candidate path."""

    model_config = ConfigDict(frozen=False, populate_by_name=True)

    # candidate_id is a legacy alias for path_id; accepted for backward compatibility
    candidate_id: Optional[str] = Field(default=None, exclude=True)
    path_id: str = Field(default="")
    provider_name: str = Field(default="")
    total_score: float = Field(..., ge=0.0, le=100.0)
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    rank: int = Field(default=1)
    rationale: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def _map_candidate_id(cls, values: Any) -> Any:
        """Map legacy candidate_id to path_id for backward compatibility."""
        if isinstance(values, dict):
            if "candidate_id" in values and not values.get("path_id"):
                values["path_id"] = values["candidate_id"]
        return values


class PathSimulationResult(BaseModel):
    """Predictive or counterfactual path simulation outcome."""

    model_config = ConfigDict(frozen=False)

    scenario: SimulationScenario = Field(...)
    path_id: str = Field(...)
    provider_name: str = Field(...)
    data_origin: DataOrigin = Field(default=DataOrigin.SIMULATED)
    expected_latency_ms: float = Field(...)
    expected_packet_loss_percent: float = Field(...)
    expected_utilization_percent: float = Field(...)
    expected_failure_risk: float = Field(...)
    expected_impact_summary: str = Field(default="")
    display_label: str = Field(default="SIMULATED / ESTIMATED")


class FailoverRecommendation(BaseModel):
    """Advisory failover recommendation decision."""

    model_config = ConfigDict(frozen=False)

    recommendation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    current_provider: str = Field(...)
    current_path_id: str = Field(default="")
    current_status: str = Field(default="HEALTHY")
    current_failure_risk: float = Field(default=0.0)
    recommended_provider: Optional[str] = Field(default=None)
    recommended_path_id: Optional[str] = Field(default=None)
    decision_status: DecisionStatus = Field(default=DecisionStatus.KEEP_CURRENT_PATH)
    expected_improvements: Dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    trust_policy_status: str = Field(default="HUMAN_APPROVAL_REQUIRED")
    execution_status: str = Field(default="NOT PERFORMED")
    rationale: List[str] = Field(default_factory=list)
    evidence_lineage: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PathDecisionResult(BaseModel):
    """Complete structured decision bundle from the Path Decision Engine."""

    model_config = ConfigDict(frozen=False)

    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = Field(...)
    current_path: Optional[PathCandidate] = Field(default=None)
    candidate_paths: List[PathCandidate] = Field(default_factory=list)
    evaluations: List[PathEvaluation] = Field(default_factory=list)
    economics: List[NetworkEconomics] = Field(default_factory=list)
    scores: List[PathScore] = Field(default_factory=list)
    simulations: List[PathSimulationResult] = Field(default_factory=list)
    recommendation: FailoverRecommendation = Field(...)
    reasoning_summary: Optional[Dict[str, Any]] = Field(default=None)
    trust_decision: Optional[Dict[str, Any]] = Field(default=None)
    premortem_summary: Optional[Dict[str, Any]] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def recommended_path(self) -> Optional[str]:
        """Backward-compatibility alias for recommendation.recommended_provider.

        Returns the canonical recommended provider name from the nested
        FailoverRecommendation without duplicating state or altering logic.
        """
        return self.recommendation.recommended_provider
