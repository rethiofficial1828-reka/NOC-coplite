"""
Domain Models and Schemas for Recommendation Subsystem.

Provides strongly typed Pydantic v2 models for recommendation records, execution plans,
rollback plans, impact assessments, CLI commands, priorities, and statistics.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class RecommendationPriority(str, Enum):
    """Priority level for executing recommendation remediation."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    URGENT = "URGENT"


class RiskLevel(str, Enum):
    """Risk level associated with executing remediation actions."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RecommendationCommand(BaseModel):
    """CLI or API command specification for execution or verification."""

    model_config = ConfigDict(frozen=False)

    command_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    command_text: str = Field(..., description="Exact CLI syntax string")
    description: str = Field(..., description="Purpose or description of command")
    target_device: str = Field(..., description="Target device or interface name")
    platform: str = Field(default="cisco_ios", description="Target platform (cisco_ios, junos, linux, etc.)")
    is_reversable: bool = Field(default=True, description="Whether command can be safely rolled back")


class RecommendationAction(BaseModel):
    """Discrete action step containing operational instructions and commands."""

    model_config = ConfigDict(frozen=False)

    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(...)
    description: str = Field(...)
    sequence_order: int = Field(default=1)
    cli_commands: List[RecommendationCommand] = Field(default_factory=list)
    verification_commands: List[RecommendationCommand] = Field(default_factory=list)


class RollbackPlan(BaseModel):
    """Plan detailing steps and commands required to revert remediation."""

    model_config = ConfigDict(frozen=False)

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    steps: List[str] = Field(default_factory=list)
    rollback_commands: List[RecommendationCommand] = Field(default_factory=list)
    estimated_rollback_duration_min: float = Field(default=2.0)


class ImpactAssessment(BaseModel):
    """Assessment of business impact, affected services, and risk level."""

    model_config = ConfigDict(frozen=False)

    business_impact: str = Field(default="LOW_BUSINESS_IMPACT")
    affected_services: List[str] = Field(default_factory=list)
    risk_level: RiskLevel = Field(default=RiskLevel.LOW)
    downtime_expected: bool = Field(default=False)


class ExecutionPlan(BaseModel):
    """Ordered sequence of remediation actions, estimated duration, and automation flag."""

    model_config = ConfigDict(frozen=False)

    actions: List[RecommendationAction] = Field(default_factory=list)
    estimated_duration_min: float = Field(default=5.0)
    automation_possible: bool = Field(default=True)


class RecommendationRecord(BaseModel):
    """Primary recommendation data model representing a remediation plan for an incident."""

    model_config = ConfigDict(frozen=False)

    recommendation_id: str = Field(..., description="Sequential ID e.g. REC-2026-000001")
    incident_id: str = Field(..., description="Target incident ID e.g. INC-2026-000001")
    device_id: str = Field(..., description="Target device ID")
    interface: str = Field(..., description="Network interface name")
    summary: str = Field(..., description="High-level remediation summary")
    priority: RecommendationPriority = Field(default=RecommendationPriority.MEDIUM)
    root_cause_hypothesis: str = Field(default="")
    recommended_actions: List[str] = Field(default_factory=list)
    execution_plan: ExecutionPlan = Field(default_factory=ExecutionPlan)
    rollback_plan: RollbackPlan = Field(default_factory=RollbackPlan)
    impact_assessment: ImpactAssessment = Field(default_factory=ImpactAssessment)
    cited_sources: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RecommendationStatistics(BaseModel):
    """Aggregated recommendation metrics summary."""

    model_config = ConfigDict(frozen=False)

    total_recommendations: int = Field(default=0)
    automated_recommendations: int = Field(default=0)
    high_priority_recommendations: int = Field(default=0)
    average_duration_min: float = Field(default=0.0)
