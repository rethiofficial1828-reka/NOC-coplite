"""
Domain Models and Schemas for Multi-Site NOC Command Center Subsystem (v1.3).

Provides strongly-typed Pydantic v2 domain models for multi-site inventory records,
site health statuses, site classifications, operator work queue items, and summary state.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from agents.incident.incident_models import IncidentSeverity, IncidentStatus
from agents.topology.topology_models import ImpactSeverity


class SiteHealthStatus(str, Enum):
    """Aggregate health classification for a network site."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    OFFLINE = "OFFLINE"
    MAINTENANCE = "MAINTENANCE"


class SiteType(str, Enum):
    """Functional role or tier classification of a network site."""

    DATACENTER = "DATACENTER"
    CAMPUS = "CAMPUS"
    REGIONAL_HUB = "REGIONAL_HUB"
    BRANCH = "BRANCH"


class SiteRecord(BaseModel):
    """Structured representation of a physical or logical network site."""

    model_config = ConfigDict(frozen=False)

    site_id: str = Field(..., description="Unique site identifier e.g. 'site-branch3'")
    site_name: str = Field(..., description="Human-readable site name e.g. 'Branch Office 3'")
    site_type: SiteType = Field(default=SiteType.BRANCH, description="Site tier / role")
    location: str = Field(default="Regional Office", description="Physical location or region")
    device_ids: List[str] = Field(default_factory=list, description="Constituent device IDs or names")
    primary_providers: List[str] = Field(default_factory=list, description="Configured primary upstream ISPs")
    backup_providers: List[str] = Field(default_factory=list, description="Configured backup upstream ISPs")
    health_status: SiteHealthStatus = Field(default=SiteHealthStatus.HEALTHY, description="Aggregate health")
    active_incidents_count: int = Field(default=0, description="Active incidents count at this site")
    critical_incidents_count: int = Field(default=0, description="Critical incidents count at this site")
    average_latency_ms: float = Field(default=15.0, description="Observed average latency in ms")
    average_loss_percent: float = Field(default=0.0, description="Observed average packet loss percentage")
    average_utilization_percent: float = Field(default=25.0, description="Average interface utilization")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional site metadata")


class QueuePriority(str, Enum):
    """Priority tiers for the Operator Work Queue."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class WorkQueueItem(BaseModel):
    """Actionable incident item presented in the operator work queue."""

    model_config = ConfigDict(frozen=False)

    queue_item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    incident_id: str = Field(..., description="Target incident ID (e.g. INC-2026-000001)")
    site_id: str = Field(..., description="Associated site identifier")
    site_name: str = Field(..., description="Associated human-readable site name")
    device_id: str = Field(..., description="Target device ID or interface key")
    interface: str = Field(..., description="Network interface name")
    title: str = Field(..., description="Incident summary title")
    priority: QueuePriority = Field(default=QueuePriority.MEDIUM, description="Computed queue priority tier")
    priority_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Composite priority score [0.0, 1.0]")
    severity: IncidentSeverity = Field(default=IncidentSeverity.MEDIUM, description="Incident severity")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Predictive failure risk score")
    blast_radius_severity: ImpactSeverity = Field(default=ImpactSeverity.LOW, description="Topology blast radius")
    time_to_impact_sec: float = Field(default=-1.0, description="Estimated time to impact in seconds")
    trust_requirement: str = Field(default="HUMAN_APPROVAL_REQUIRED", description="Autonomy policy requirement")
    status: IncidentStatus = Field(default=IncidentStatus.NEW, description="Lifecycle status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlated_group_id: Optional[str] = Field(default=None, description="Associated cross-site group ID")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CorrelationType(str, Enum):
    """Basis for cross-site incident correlation."""

    SHARED_PROVIDER = "SHARED_PROVIDER"
    SHARED_TOPOLOGY_DEPENDENCY = "SHARED_TOPOLOGY_DEPENDENCY"
    SIMILAR_FAILURE_SIGNATURE = "SIMILAR_FAILURE_SIGNATURE"
    SYNCHRONIZED_TEMPORAL = "SYNCHRONIZED_TEMPORAL"


class CorrelatedIncidentGroup(BaseModel):
    """A cluster of interrelated incidents spanning multiple sites or devices."""

    model_config = ConfigDict(frozen=False)

    group_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_type: CorrelationType = Field(..., description="Primary correlation dimension")
    title: str = Field(..., description="Short summary title of the correlated cluster")
    description: str = Field(..., description="Explicit deterministic rationale for correlation")
    incident_ids: List[str] = Field(default_factory=list, description="Associated incident IDs")
    affected_site_ids: List[str] = Field(default_factory=list, description="Impacted site IDs")
    affected_devices: List[str] = Field(default_factory=list, description="Impacted device/interface keys")
    shared_dependency: str = Field(..., description="Common provider, transit node, or dependency key")
    correlation_confidence: float = Field(default=0.85, ge=0.0, le=1.0, description="Derived confidence [0.0, 1.0]")
    primary_root_cause_hypothesis: str = Field(default="", description="Root-cause hypothesis")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="Preserved supporting evidence IDs")
    contradicting_evidence_ids: List[str] = Field(default_factory=list, description="Preserved contradicting evidence IDs")
    recommended_coordinating_action: str = Field(default="", description="Recommended operational action")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    secondary_correlation_types: List[CorrelationType] = Field(default_factory=list, description="Corroborating dimensions")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MultiSiteSummaryState(BaseModel):
    """Top-level command center fleet state snapshot."""

    model_config = ConfigDict(frozen=False)

    total_sites: int = Field(default=0, description="Total configured sites count")
    healthy_sites: int = Field(default=0, description="Count of sites in HEALTHY state")
    degraded_sites: int = Field(default=0, description="Count of sites in DEGRADED state")
    critical_sites: int = Field(default=0, description="Count of sites in CRITICAL state")
    offline_sites: int = Field(default=0, description="Count of sites in OFFLINE state")
    total_active_incidents: int = Field(default=0, description="Total active incidents across all sites")
    critical_active_incidents: int = Field(default=0, description="Total critical incidents across all sites")
    sites: List[SiteRecord] = Field(default_factory=list, description="All site records with current health")
    work_queue: List[WorkQueueItem] = Field(default_factory=list, description="Prioritized operator queue items")
    correlated_groups: List[CorrelatedIncidentGroup] = Field(default_factory=list, description="Correlated incident clusters")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
