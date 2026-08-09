"""
Strongly-typed Pydantic schemas for the Enterprise Collector Integration Layer.

Defines collector state, source selection modes, metadata, schedules,
capabilities, and health models for pluggable telemetry collection.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

# Re-export TelemetryPacket for convenience
from agents.schemas.schemas import TelemetryPacket


class CollectorState(str, Enum):
    """Lifecycle state of a telemetry collector."""

    UNINITIALIZED = "UNINITIALIZED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    TERMINATED = "TERMINATED"


class SourceMode(str, Enum):
    """Ingestion source selection mode for the enterprise data layer."""

    SIMULATION = "SIMULATION"
    LIVE = "LIVE"
    HYBRID = "HYBRID"
    FAILOVER = "FAILOVER"


class CollectorSchedule(BaseModel):
    """Configuration for collector polling frequency and execution parameters."""

    model_config = ConfigDict(frozen=False)

    interval_seconds: float = Field(default=5.0, gt=0, description="Polling interval in seconds")
    enabled: bool = Field(default=True, description="Whether collector is active")
    priority: int = Field(default=100, ge=1, description="Execution priority (1 = highest)")
    timeout_seconds: float = Field(default=10.0, gt=0, description="Collection timeout in seconds")
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts on failure")
    backoff_factor: float = Field(default=1.5, ge=1.0, description="Exponential backoff factor for retries")


class CollectorCapabilities(BaseModel):
    """Capabilities supported by a specific collector implementation."""

    model_config = ConfigDict(frozen=False)

    supports_streaming: bool = Field(default=False, description="Supports real-time streaming")
    supports_polling: bool = Field(default=True, description="Supports interval-based polling")
    supports_batch: bool = Field(default=True, description="Supports batch packet collection")
    supports_filtering: bool = Field(default=True, description="Supports metric/device filtering")
    requires_auth: bool = Field(default=False, description="Requires authentication credentials")
    protocol: str = Field(default="internal", description="Primary protocol (snmp, syslog, rest, etc.)")


class CollectorMetadata(BaseModel):
    """Metadata describing a telemetry collector's identity and capabilities."""

    model_config = ConfigDict(frozen=False)

    name: str = Field(..., description="Unique collector name identifier")
    collector_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique collector instance ID")
    version: str = Field(default="1.0.0", description="Semantic version string")
    description: str = Field(default="", description="Detailed description of collector responsibility")
    source_type: str = Field(default="custom", description="Telemetry source classification")
    supported_metrics: List[str] = Field(
        default_factory=lambda: ["utilization", "latency", "jitter", "drops", "errors"],
        description="List of metric keys produced",
    )
    author: str = Field(default="NOC Copilot Core Team", description="Author or organization")
    config: Dict[str, Any] = Field(default_factory=dict, description="Collector-specific configuration params")


class CollectorHealth(BaseModel):
    """Operational health snapshot of a telemetry collector."""

    model_config = ConfigDict(frozen=False)

    collector_id: str = Field(..., description="Collector instance ID")
    collector_name: str = Field(..., description="Collector name")
    state: CollectorState = Field(default=CollectorState.UNINITIALIZED, description="Current operational state")
    is_healthy: bool = Field(default=True, description="Overall health status flag")
    total_collections: int = Field(default=0, description="Total collection attempts")
    successful_collections: int = Field(default=0, description="Total successful collections")
    failed_collections: int = Field(default=0, description="Total failed collections")
    consecutive_failures: int = Field(default=0, description="Current streak of failed collections")
    last_collection_timestamp: Optional[datetime] = Field(default=None, description="Timestamp of last collection attempt")
    last_success_timestamp: Optional[datetime] = Field(default=None, description="Timestamp of last success")
    last_failure_timestamp: Optional[datetime] = Field(default=None, description="Timestamp of last failure")
    last_latency_ms: float = Field(default=0.0, description="Latency of last collection in ms")
    avg_latency_ms: float = Field(default=0.0, description="Average collection latency in ms")
    total_latency_ms: float = Field(default=0.0, description="Cumulative latency in ms")
    last_error: Optional[str] = Field(default=None, description="Last error message if failed")
    packets_collected: int = Field(default=0, description="Total TelemetryPacket instances emitted")
    collection_frequency_hz: float = Field(default=0.0, description="Calculated collection frequency")
    availability_percent: float = Field(default=100.0, ge=0.0, le=100.0, description="Availability ratio (success/total)")
