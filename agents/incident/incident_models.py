"""
Domain Models and Schemas for Incident Management Subsystem.

Provides strongly typed Pydantic v2 models for incident records, timeline entries,
comments, assignments, severity levels, status states, and statistics.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class IncidentSeverity(str, Enum):
    """Incident severity classification levels."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(str, Enum):
    """Lifecycle status states for an incident."""

    NEW = "NEW"
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    MITIGATED = "MITIGATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class IncidentTimeline(BaseModel):
    """Audit timeline event recorded for incident lifecycle changes."""

    model_config = ConfigDict(frozen=False)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    incident_id: str = Field(..., description="Target incident identifier (e.g. INC-2026-000001)")
    event_type: str = Field(..., description="Type of event (e.g. CREATED, SEVERITY_CHANGED, STATUS_CHANGED)")
    description: str = Field(..., description="Human readable event summary")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    author: str = Field(default="System", description="User or service initiating state change")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context attributes")


class IncidentComment(BaseModel):
    """Comment entry added to an incident."""

    model_config = ConfigDict(frozen=False)

    comment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    incident_id: str = Field(...)
    author: str = Field(...)
    comment_text: str = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IncidentAssignment(BaseModel):
    """Ownership assignment for an incident."""

    model_config = ConfigDict(frozen=False)

    assigned_user: Optional[str] = Field(default="Unassigned", description="User ID or name")
    assigned_team: Optional[str] = Field(default="NOC-Operations", description="Team or queue name")
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IncidentRecord(BaseModel):
    """Primary incident data model representing a network fault or predictive risk issue."""

    model_config = ConfigDict(frozen=False)

    incident_id: str = Field(..., description="Sequential unique identifier e.g. INC-2026-000001")
    device_id: str = Field(..., description="Target device ID or interface key")
    interface: str = Field(..., description="Network interface name")
    incident_type: str = Field(default="GENERAL_ANOMALY", description="Categorical incident type")
    title: str = Field(..., description="Short summary title")
    description: str = Field(default="", description="Detailed description")
    severity: IncidentSeverity = Field(default=IncidentSeverity.MEDIUM)
    status: IncidentStatus = Field(default=IncidentStatus.NEW)
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    time_to_impact: float = Field(default=-1.0)
    contributing_signals: List[str] = Field(default_factory=list)
    assignment: IncidentAssignment = Field(default_factory=IncidentAssignment)
    timeline: List[IncidentTimeline] = Field(default_factory=list)
    comments: List[IncidentComment] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = Field(default=None)
    closed_at: Optional[datetime] = Field(default=None)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IncidentStatistics(BaseModel):
    """Composite incident operational metrics summary."""

    model_config = ConfigDict(frozen=False)

    total_incidents: int = Field(default=0)
    open_incidents: int = Field(default=0)
    closed_incidents: int = Field(default=0)
    critical_incidents: int = Field(default=0)
    average_resolution_time_sec: float = Field(default=0.0)
    creation_rate_per_hour: float = Field(default=0.0)
    update_rate_per_hour: float = Field(default=0.0)
