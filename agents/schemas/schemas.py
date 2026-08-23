"""
Strongly-typed Pydantic schemas for the Atomic Agent Framework.

Provides domain models, agent metadata, runtime metrics, capability flags,
and shared payloads used by agents, orchestrators, and event buses.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, ConfigDict


class AgentState(str, Enum):
    """Execution state of an agent lifecycle."""

    UNINITIALIZED = "UNINITIALIZED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TERMINATED = "TERMINATED"


class CapabilityFlags(BaseModel):
    """Declarative capability flags for agent execution modes."""

    model_config = ConfigDict(frozen=False)

    supports_async: bool = False
    supports_batch: bool = False
    supports_streaming: bool = False
    supports_parallel_execution: bool = False
    supports_gpu: bool = False
    supports_cpu: bool = True


class AgentMetadata(BaseModel):
    """Metadata describing an agent's identity, version, and dependencies."""

    model_config = ConfigDict(frozen=False)

    name: str = Field(..., description="Unique agent name identifier")
    version: str = Field(default="1.0.0", description="Semantic version string")
    description: str = Field(default="", description="Detailed description of agent responsibility")
    author: str = Field(default="NOC Copilot Core Team", description="Author or vendor")
    api_version: str = Field(default="v1", description="Framework API compatibility version")
    dependencies: List[str] = Field(default_factory=list, description="Names of prerequisite agents")
    tags: List[str] = Field(default_factory=list, description="Categorical classification tags")
    supported_platforms: List[str] = Field(
        default_factory=lambda: ["linux", "windows", "darwin"],
        description="Supported operating systems",
    )
    minimum_python: str = Field(default="3.10", description="Minimum supported Python version")
    license: str = Field(default="Proprietary", description="License specification")
    capabilities: CapabilityFlags = Field(
        default_factory=CapabilityFlags, description="Execution capabilities"
    )


class AgentMetrics(BaseModel):
    """Real-time runtime metrics tracked per agent execution."""

    model_config = ConfigDict(frozen=False)

    execution_count: int = Field(default=0, description="Total number of executions")
    total_execution_time_ms: float = Field(default=0.0, description="Cumulative execution time in ms")
    average_runtime_ms: float = Field(default=0.0, description="Average execution duration in ms")
    last_runtime_ms: float = Field(default=0.0, description="Duration of the most recent execution in ms")
    failure_count: int = Field(default=0, description="Total failed executions")
    success_count: int = Field(default=0, description="Total successful executions")
    current_state: AgentState = Field(default=AgentState.UNINITIALIZED, description="Current agent state")
    memory_bytes_placeholder: int = Field(default=0, description="Memory consumption placeholder")
    cpu_percent_placeholder: float = Field(default=0.0, description="CPU consumption placeholder")


class TelemetryPacket(BaseModel):
    """Strongly typed telemetry sample packet."""

    packet_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str = Field(..., description="Monitored device identifier")
    interface: str = Field(..., description="Network interface name")
    metrics: Dict[str, float] = Field(default_factory=dict, description="Metric key-value pairs")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional contextual headers")


class PredictionResult(BaseModel):
    """Predictive ML risk assessment result."""

    prediction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    interface: str = Field(..., description="Evaluated interface name")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Predicted failure risk score (0.0 to 1.0)")
    time_to_impact: float = Field(..., description="Estimated minutes until impact (-1.0 if low risk)")
    contributing_signals: List[str] = Field(default_factory=list, description="Top metrics driving risk")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Model prediction confidence")


class DeviceHealth(BaseModel):
    """Device operational health status snapshot."""

    device_id: str = Field(...)
    name: str = Field(...)
    status: str = Field(default="healthy", description="Status label (healthy, degraded, critical)")
    health_score: float = Field(default=100.0, ge=0.0, le=100.0, description="Composite health index")
    active_incidents: int = Field(default=0, description="Number of active incidents")
    metrics: Dict[str, Any] = Field(default_factory=dict)


class Incident(BaseModel):
    """Network anomaly or fault incident representation."""

    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(...)
    severity: str = Field(default="WARNING", description="Severity (INFO, WARNING, CRITICAL, SEVERE)")
    status: str = Field(default="OPEN", description="Status (OPEN, INVESTIGATING, MITIGATED, RESOLVED)")
    source: str = Field(..., description="Source component or agent")
    affected_entities: List[str] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = Field(default_factory=dict)


class Recommendation(BaseModel):
    """Copilot recommendation action object."""

    recommendation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    incident_id: Optional[str] = Field(default=None)
    title: str = Field(...)
    action_steps: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    rationale: str = Field(default="")
    cited_sources: List[str] = Field(default_factory=list)


class TopologyState(BaseModel):
    """Network topology state representation."""

    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    links: List[Dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionContext(BaseModel):
    """Execution context passed across workflow execution steps."""

    context_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parameters: Dict[str, Any] = Field(default_factory=dict)
    payload: Dict[str, Any] = Field(default_factory=dict)
    results: Dict[str, Any] = Field(default_factory=dict)
    shared_state: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
